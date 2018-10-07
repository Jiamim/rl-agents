from gym import logger
import numpy as np

from rl_agents.agents.common import safe_deepcopy_env
from rl_agents.agents.tree_search.abstract import Node, AbstractTreeSearchAgent, AbstractPlanner


class OLOPAgent(AbstractTreeSearchAgent):
    """
        An agent that uses Open Loop Optimistic Planning to plan a sequence of actions in an MDP.
    """
    def make_planner(self):
        return OLOP(self.env, self.config)


class OLOP(AbstractPlanner):
    """
       An implementation of Open Loop Optimistic Planning.
    """
    def __init__(self, env, config=None):
        self.leaves = None
        self.env = env
        super(OLOP, self).__init__(config)

    def make_root(self):
        root, self.leaves = self.build_tree(self.env.action_space.n)
        return root

    @staticmethod
    def horizon(episodes, gamma):
        return int(np.ceil(np.log(episodes) / (2 * np.log(1 / gamma))))

    def allocate_budget(self):
        for episodes in range(1, 1000):
            if episodes * OLOP.horizon(episodes, self.config["gamma"]) > self.config["budget"]:
                self.config["episodes"] = episodes - 1
                self.config["horizon"] = OLOP.horizon(self.config["episodes"], self.config["gamma"])
                break
        else:
            raise ValueError("Could not split budget {} with gamma {}".format(self.config["budget"], self.config["gamma"]))

    def build_tree(self, branching_factor):
        root = OLOPNode(parent=None, planner=self)
        leaves = [root]
        if "horizon" not in self.config:
            self.allocate_budget()
        for _ in range(self.config["horizon"]):
            next_leaves = []
            for leaf in leaves:
                leaf.expand(branching_factor)
                next_leaves += leaf.children.values()
            leaves = next_leaves
        return root, leaves

    def run(self, state):
        """
            Run an OLOP episode.

            Find the leaf with highest upper bound value, and sample the corresponding action sequence.

        :param state: the initial environment state
        """
        # Compute B-values
        list(Node.breadth_first_search(self.root, operator=self.compute_u_values, condition=None))
        sequences = list(map(OLOP.compute_b_values, self.leaves))

        # Pick best action sequence
        best_sequence = list(self.leaves[np.argmax(sequences)].path())

        # Execute sequence and collect rewards
        node = self.root
        terminal = False
        for action in best_sequence:
            observation, reward, done, _ = state.step(action)
            terminal = terminal or done
            reward = reward if not terminal else 0
            node = node.children[action]
            node.update(reward, self.config["episodes"])

    def compute_u_values(self, node, path):
        """
            Compute the upper bound value of the action sequence at a given node.

            It represents the maximum admissible reward over trajectories that start with this particular sequence.
            It is computed by summing upper bounds of intermediate rewards along the sequence, and an upper bound
            of the remaining rewards over possible continuations of the sequence.
        :param node: a node in the look-ahead tree
        :param path: the path from the root to the node (unused)
        :return: the path from the root to the node, and the node value.
        """
        # Upper bound of the reward-to-go after this node
        node.value = self.config["gamma"] ** (len(path) + 1) / (1 - self.config["gamma"])
        node_t = node
        for t in np.arange(len(path), 0, -1):  # from current node up to the root
            node.value += self.config["gamma"]**t * node_t.mu_ucb  # upper bound of the node mean reward
            node_t = node_t.parent
        return path, node.value

    @staticmethod
    def compute_b_values(node):
        """
            Sharpen the upper-bound value of the action sequences at the tree leaves.

            By computing the min over intermediate upper-bounds along the sequence, that must all be satisfied.
        :param node: a node in the look-ahead tree
        :return:the sharpened upper-bound
        """
        node_t = node
        min_ucb = node.value
        while node_t.parent:
            min_ucb = min(min_ucb, node_t.value)
            node_t = node_t.parent
        return min_ucb

    def plan(self, state, observation):
        for i in range(self.config['episodes']):
            if (i+1) % 10 == 0:
                logger.debug('{} / {}'.format(i+1, self.config['episodes']))
            self.run(safe_deepcopy_env(state))

        return self.get_plan()


class OLOPNode(Node):
    def __init__(self, parent, planner):
        super(OLOPNode, self).__init__(parent, planner)

        self.cumulative_reward = 0
        """ Sum of all rewards received at this node. """

        self.mu_ucb = np.infty
        """ Upper bound of the node mean reward. """

    def selection_rule(self):
        # Tie best counts by best value
        actions = list(self.children.keys())
        counts = Node.all_argmax([self.children[a].count for a in actions])
        return actions[max(counts, key=(lambda i: self.children[actions[i]].get_value()))]

    def update(self, reward, episodes):
        if not 0 <= reward <= 1:
            raise ValueError("This planner assumes that all rewards are normalized in [0, 1]")
        self.cumulative_reward += reward
        self.count += 1
        self.mu_ucb = self.cumulative_reward / self.count + np.sqrt(2 * np.log(episodes) / self.count)