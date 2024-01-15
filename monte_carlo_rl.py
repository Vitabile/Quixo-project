from game import Game, Move, Player
from typing import Literal
import numpy as np
import pickle
import math
from random import random, choice
from tqdm import trange
from random_player import RandomPlayer
from investigate_game import InvestigateGame, MissNoAddDict
from min_max import MinMaxPlayer
from symmetry import Symmetry
from copy import deepcopy


class MonteCarloRLPlayer(Player):
    """
    Class representing player who learns to play thanks to the Monte Carlo-learning technique.
    """

    def __init__(
        self,
        n_episodes: int = 200_000,
        gamma: float = 0.95,
        alpha: float = 0.1,
        min_exploration_rate: float = 0.01,
        exploration_decay_rate: float = 3e-5,
        minmax: bool = False,
        switch_ratio: int = 0.9,
        depth: int = 1,
        symmetries: bool = False,
    ) -> None:
        """
        The Monte Carlo-learning player constructor.

        Args:
            n_episodes: the number of episodes for the training phase;
            gamma: the discount rate of the Bellman equation;
            min_exploration_rate: the minimum rate for exploration during the training phase;
            exploration_decay_rate: the exploration decay rate used during the training;
            minmax: decide if the training must be performed also on minmax.
            switch_ratio: define the moment in which we should play against minmax;
            depth: maximum depth of the Min-Max search tree;
            symmetries: flag to consider the symmetries or not.

        Returns:
            None.
        """
        super().__init__()
        self._state_values = MissNoAddDict(float)  # define the State-value function
        self._n_episodes = n_episodes  # define the number of episodes for the training phase
        self._gamma = gamma  # define the discount rate of the Bellman equation
        self._alpha = alpha  # define how much information to incorporate from the new experience
        self._exploration_rate = 1  # define the exploration rate for the training phase
        self._min_exploration_rate = (
            min_exploration_rate  # define the minimum rate for exploration during the training phase
        )
        self._exploration_decay_rate = (
            exploration_decay_rate  # define the exploration decay rate used during the training
        )
        self._minmax = minmax  # define if we want to play also against minmax
        self._switch_ratio = switch_ratio  # define the moment in which minmax plays against us
        self._depth = depth  # define the depth for minmax
        self._symmetries = symmetries  # choose if play symmetries should be considered
        self._rewards = []  # list of the rewards obtained during training

    @property
    def rewards(self) -> list[int]:
        """
        Return a copy of the rewards obtained during training

        Args:
            None.

        Returns:
            The training rewards are returned.
        """
        return tuple(self._rewards)

    def _game_reward(self, player: 'InvestigateGame', winner: int) -> Literal[-10, -1, 10]:
        """
        Calculate the reward based on how the game ended.

        Args:
            player: the winning player;
            winner: the winner's player id.

        Returns:
            The game reward is returned.
        """
        # if no one wins
        if winner == -1:
            # return small penalty
            return -1
        # if the agent is the winner
        if self == player:
            # give a big positive reward
            return 10
        # give a big negative reward, otherwise
        return -10

    def _map_state_to_index(self, game: 'Game', player_id: int) -> tuple['InvestigateGame', str, int]:
        """
        Given a game state, this function translates it into an index to access the Q_table.

        Args:
            game: a game instance;
            player_id: my player's id.

        Returns:
            The corresponding canonical game, its representation and index in the list
            returned by 'Symmetry.get_transformed_states(game)' are returned.
        """

        # take trasformed states
        trasformed_states = Symmetry.get_transformed_states(game)

        # list of mapped states to a string in base 3
        trasformed_states_repr_index = [
            trasformed_state.get_hashable_state(player_id) for trasformed_state in trasformed_states
        ]

        # trasformation index
        trasformation_index = np.argmin(trasformed_states_repr_index)

        return (
            trasformed_states[trasformation_index],
            trasformed_states_repr_index[trasformation_index],
            trasformation_index,
        )

    def _update_state_values(self, state_repr_index: str, return_of_rewards: float) -> None:
        """
        Update the Q_table according to the Monte Carlo-learning technique.

        Args:
            state_repr_index: the current state index;
            action: the performed action;
            return_of_rewards: the return of rewards for the current state.

        Returns:
            None.
        """
        # update the state-value mapping table
        self._state_values[state_repr_index] = self._state_values[state_repr_index] + self._alpha * (
            return_of_rewards - self._state_values[state_repr_index]
        )

    def _step_training(
        self,
        game: 'InvestigateGame',
        player_id: int,
    ) -> tuple[tuple[tuple[int, int], Move], 'InvestigateGame']:
        """
        Construct a move during the training phase to update the Q_table.

        Args:
            game: a game instance;
            player_id: my player's id.

        Returns:
            A move to play is returned.
        """

        # get all possible transitions
        transitions = game.generate_possible_transitions(player_id)

        # create transition with canonical states
        canonical_transitions = []
        for a, state in transitions:
            states = Symmetry.get_transformed_states(state)
            states = [state.get_hashable_state(player_id) for state in states]
            canonical_transitions.append((a, state, min(states)))

        # randomly perform exploration
        if random() < self._exploration_rate:
            # choose a random transition
            action, next_state, canonical_repr_index = choice(canonical_transitions)
        # perform eploitation, otherwise
        else:
            # take the action with min return of rewards of the oppenent
            action, next_state, canonical_repr_index = max(
                canonical_transitions, key=lambda t: self._state_values[t[2]]
            )

        return action, next_state, canonical_repr_index

    def make_move(self, game: 'Game') -> tuple[tuple[int, int], Move]:
        """
        Construct a move to be played according to the Q_table.

        Args:
            game: a game instance.

        Returns:
            A move to play is returned.
        """
        # create seperate instance of a game for investigation
        game = InvestigateGame(game)
        # get my id
        player_id = game.get_current_player()
        # get all possible transitions
        transitions = game.generate_possible_transitions(player_id)

        # create transition with canonical states
        canonical_transitions = []
        for a, state in transitions:
            states = Symmetry.get_transformed_states(state)
            states = [state.get_hashable_state(player_id) for state in states]
            canonical_transitions.append((a, min(states)))

        # if one of the following states is known
        if any([t[1] in self._state_values for t in canonical_transitions]):
            # take the action with min return of rewards of the oppenent
            action, _ = max(canonical_transitions, key=lambda t: self._state_values[t[1]])
        else:
            # choose a random action
            action, _ = choice(transitions)

        # return the action
        return action

    def train(self, max_steps_draw: int) -> None:
        """
        Train the Monte Carlo-learning player.

        Args:
            max_steps_draw: define the maximum number of steps before
                            claiming a draw.

        Returns:
            None.
        """

        # define how many episodes to run
        pbar_episodes = trange(self._n_episodes)
        # define the random tuples
        player_tuples = ((RandomPlayer(), self), (self, RandomPlayer()))

        # if we want to play also against minmax
        if self._minmax:
            # define the minmax players
            minmax_players = (
                (MinMaxPlayer(player_id=0, depth=self._depth, symmetries=self._symmetries), self),
                (self, MinMaxPlayer(player_id=1, depth=self._depth, symmetries=self._symmetries)),
            )

        # for each episode
        for episode in pbar_episodes:
            # define a new game
            game = InvestigateGame(Game())

            # switch the players if it is the moment
            if self._minmax and math.isclose(self._switch_ratio, episode / self._n_episodes):
                player_tuples = minmax_players

            # define the trajectory
            trajectory = []

            # define a variable to indicate if there is a winner
            winner = -1
            # change player tuple order
            player_tuples = (player_tuples[1], player_tuples[0])
            # change players order
            players = player_tuples[-1]
            # define the current player index
            player_idx = 1

            # save last action
            last_action = None
            # define counter to terminate if we are in a loop
            counter = 0

            # if we can still play
            while winner < 0 and counter < max_steps_draw:
                # change player
                player_idx = (player_idx + 1) % 2
                player = players[player_idx]

                # if it is our turn
                if self == player:
                    # get an action
                    action, game, canonical_state_repr_index = self._step_training(game, player_idx)

                    # update the trajectory
                    trajectory.append((canonical_state_repr_index, 0))

                    # if we play the same action as before
                    if last_action == action:
                        # increment the counter
                        counter += 1
                    # otherwise
                    else:
                        # save the new last action
                        last_action = action
                        # reset the counter
                        counter = 0

                # if it is the opponent turn
                else:
                    # define a variable to check if the chosen move is ok or not
                    ok = False
                    # while the chosen move is not ok
                    while not ok:
                        # get a move
                        move = player.make_move(game)
                        # perform the move
                        ok = game._Game__move(*move, player_idx)

                # check if there is a winner
                winner = game.check_winner()

            # update the exploration rate
            self._exploration_rate = np.clip(
                np.exp(-self._exploration_decay_rate * episode), self._min_exploration_rate, 1
            )

            # delete last tuple in trajectory
            trajectory.pop()
            # get the game reward
            reward = self._game_reward(player, winner)
            # update the trajectory
            trajectory.append((canonical_state_repr_index, reward))

            # update the rewards history
            self._rewards.append(reward)

            # set the current return of rewards
            return_of_rewards = 0
            # for all tuples in trajectory
            for state_repr_index, reward in trajectory[::-1]:
                # update the return of rewards
                return_of_rewards = reward + self._gamma * return_of_rewards
                # update the action-value function
                self._update_state_values(state_repr_index, return_of_rewards)

            pbar_episodes.set_description(
                f"# current mean rewards: {sum(self._rewards) / (episode+1):.2f} - # explored states: {len(self._state_values):,} - Current exploration rate: {self._exploration_rate:2f}"
            )

        print(f'** Last 1_000 episodes - Mean rewards value: {sum(self._rewards[-1_000:]) / 1_000:.2f} **')
        print(f'** Last rewards value: {self._rewards[-1]:} **')

    def save(self, path: str) -> None:
        """
        Serialize the current Monte Carlo learning player's state.

        Args:
            path: location where to save the player's state.

        Returns: None.
        """
        # serialize the Monte Carlo learning player
        with open(path, 'wb') as f:
            pickle.dump(self.__dict__, f)

    def load(self, path: str) -> None:
        """
        Load a Monte Carlo earning player's state into the current player.

        Args:
            path: location from which to load the player's state.

        Returns: None.
        """
        # load the serialized Monte Carlo learning player
        with open(path, 'rb') as f:
            self.__dict__ = pickle.load(f)


if __name__ == '__main__':
    # create the Q-learning player
    monte_carlo_rl_agent = MonteCarloRLPlayer(n_episodes=500_000, exploration_decay_rate=1e-5)
    # train the Q-learning player
    monte_carlo_rl_agent.train(max_steps_draw=10)
    # serialize the Q-learning player
    monte_carlo_rl_agent.save('agents/monte_carlo_rl_agent_4.pkl')
