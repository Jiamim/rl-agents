import numpy as np

from rl_agents.agents.common.abstract import AbstractAgent


class ValueIterationAgent(AbstractAgent):
    def __init__(self, env, config=None):
        super(ValueIterationAgent, self).__init__(config)
        self.finite_mdp = self.is_finite_mdp(env)
        if self.finite_mdp:
            self.mdp = env.mdp
        elif not self.finite_mdp and hasattr(env, "to_finite_mdp"):
            self.mdp = env.to_finite_mdp()
        else:
            raise TypeError("Environment must be of type finite_mdp.envs.finite_mdp.FiniteMDPEnv or handle a conversion"
                            "method called 'to_finite_mdp' to such a type.")
        self.env = env

    @classmethod
    def default_config(cls):
        return dict(gamma=1.0,
                    iterations=100)

    def act(self, state):
        # If the environment is not a finite mdp, it must be converted to one and the state must be recovered.
        if not self.finite_mdp:
            self.mdp = self.env.to_finite_mdp()
            state = self.mdp.state
        return np.argmax(self.state_action_value()[state, :])

    def state_value(self):
        return self.fixed_point_iteration(
            lambda v: ValueIterationAgent.best_action_value(self.bellman_expectation(v)),
            np.zeros((self.mdp.transition.shape[0],)))

    def state_action_value(self):
        return self.fixed_point_iteration(
            lambda q: self.bellman_expectation(ValueIterationAgent.best_action_value(q)),
            np.zeros((self.mdp.transition.shape[0:2])))

    @staticmethod
    def best_action_value(action_values):
        return action_values.max(axis=-1)

    def bellman_expectation(self, value):
        if self.mdp.mode == "deterministic":
            next_v = value[self.mdp.transition]
        elif self.mdp.mode == "stochastic":
            next_v = (self.mdp.transition * value.reshape((1, 1, value.size))).sum(axis=-1)
        else:
            raise ValueError("Unknown mode")
        next_v[self.mdp.terminal] = 0
        return self.mdp.reward + self.config["gamma"] * next_v

    def fixed_point_iteration(self, operator, initial):
        value = initial
        for _ in range(self.config["iterations"]):
            next_value = operator(value)
            if np.allclose(value, next_value):
                break
            value = next_value
        return value

    @staticmethod
    def is_finite_mdp(env):
        try:
            finite_mdp = __import__("finite_mdp.envs.finite_mdp_env")
            if isinstance(env, finite_mdp.envs.finite_mdp_env.FiniteMDPEnv):
                return True
        except (ModuleNotFoundError, TypeError):
            return False

    def plan_trajectory(self, state, horizon=10):
        action_value = self.state_action_value()
        states, actions = [], []
        for _ in range(horizon):
            action = np.argmax(action_value[state])
            states.append(state)
            actions.append(action)
            state = self.mdp.next_state(state, action)
            if self.mdp.terminal[state]:
                states.append(state)
                actions.append(None)
                break
        return states, actions

    def record(self, state, action, reward, next_state, done, info):
        pass

    def reset(self):
        pass

    def seed(self, seed=None):
        pass

    def save(self, filename):
        raise NotImplementedError()

    def load(self, filename):
        raise NotImplementedError()
