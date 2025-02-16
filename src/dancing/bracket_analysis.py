#!/usr/bin/env python
# -*-coding:utf-8 -*-
'''
@File    :   bracket_analysis.py 
@Time    :   2024/02/13
@Author  :   Taylor Firman
@Version :   0.1.0
@Contact :   tefirman@gmail.com
@Desc    :   Analyzing trends in March Madness bracket pool simulations
'''

from typing import List
import pandas as pd
from collections import defaultdict
from dancing.wn_cbb_scraper import Standings
from dancing.cbb_brackets import Bracket, Pool
from dancing.dancing_integration import create_teams_from_standings
from datetime import datetime

class BracketAnalysis:
    """Class for analyzing trends across multiple bracket pool simulations"""
    
    # Define round order as class constant
    ROUND_ORDER = [
        "First Round",
        "Second Round", 
        "Sweet 16",
        "Elite 8",
        "Final Four",
        "Championship"
    ]
    
    def __init__(self, standings: Standings, num_pools: int = 100):
        """
        Initialize analysis with standings data
        
        Args:
            standings: Warren Nolan standings data
            num_pools: Number of pools to simulate for analysis
        """
        self.standings = standings
        self.num_pools = num_pools
        self.pools: List[Pool] = []
        self.winning_brackets: List[Bracket] = []
        self.all_results = pd.DataFrame()
        
    def simulate_pools(self, entries_per_pool: int = 10) -> None:
        """
        Simulate multiple bracket pools
        
        Args:
            entries_per_pool: Number of entries in each pool
        """
        print(f"Beginning simulation, {datetime.now()}")
        for i in range(self.num_pools):
            # Status report
            if (i + 1)%100 == 0:
                print(f"Simulation {i + 1} out of {self.num_pools}, {datetime.now()}")

            # Create actual bracket for this pool
            actual_bracket = create_teams_from_standings(self.standings)
            pool = Pool(actual_bracket)
            
            # Create entries with varying upset factors
            upset_factors = [0.1 + (j/entries_per_pool)*0.3 for j in range(entries_per_pool)]
            for j, upset_factor in enumerate(upset_factors):
                entry_bracket = create_teams_from_standings(self.standings)
                for game in entry_bracket.games:
                    # Modify simulate_game method to use this entry's upset factor
                    game.upset_factor = upset_factor
                entry_name = f"Entry_{j+1}"
                pool.add_entry(entry_name, entry_bracket)
            
            # Store pool
            self.pools.append(pool)
            
            # Simulate and store results
            pool_results = pool.simulate_pool(num_sims=1000)
            
            # Store winning bracket from this pool
            winning_entry = pool_results.iloc[0]['name']
            winning_bracket = [entry[1] for entry in pool.entries 
                             if entry[0] == winning_entry][0]
            self.winning_brackets.append(winning_bracket)
            
            # Store full results
            pool_results['pool_id'] = i
            self.all_results = pd.concat([self.all_results, pool_results])
            
    def analyze_upsets(self) -> pd.DataFrame:
        """
        Analyze upset patterns in winning brackets
        
        Returns:
            DataFrame containing upset statistics by round, ordered chronologically
        """
        upset_stats = defaultdict(list)
        
        for bracket in self.winning_brackets:
            results = bracket.simulate_tournament()
            
            for round_name, teams in results.items():
                if round_name != "Champion":  # Skip final result
                    # Count upsets (when lower seed beats higher seed)
                    upsets = sum(1 for team in teams 
                               if any(t for t in bracket.games 
                                    if t.winner == team and t.winner.seed > t.team1.seed))
                    upset_stats[round_name].append(upsets)
        
        # Convert to DataFrame
        stats_df = pd.DataFrame(upset_stats)
        
        # Calculate summary statistics
        summary = pd.DataFrame({
            'round': stats_df.columns,
            'avg_upsets': stats_df.mean(),
            'std_upsets': stats_df.std(),
            'min_upsets': stats_df.min(),
            'max_upsets': stats_df.max()
        })
        
        # Sort by predefined round order
        summary['round_order'] = summary['round'].map({round_name: i for i, round_name in enumerate(self.ROUND_ORDER)})
        summary = summary.sort_values('round_order').drop('round_order', axis=1)
        
        return summary
    
    def find_common_underdogs(self) -> pd.DataFrame:
        """
        Identify most common upset teams by round, where an upset is defined
        as a team advancing further than their seed traditionally would.
        
        Expected seeds by round:
        - First Round: All seeds (no upsets possible)
        - Second Round: Seeds 1-8
        - Sweet 16: Seeds 1-4
        - Elite 8: Seeds 1-2
        - Final Four: Seeds 1
        - Championship: Seeds 1
        
        Returns:
            DataFrame containing most frequent upset teams, grouped by round
        """
        # Define expected maximum seed for each round
        EXPECTED_MAX_SEEDS = {
            "First Round": 16,  # No upsets possible
            "Second Round": 8,
            "Sweet 16": 4,
            "Elite 8": 2,
            "Final Four": 1,
            "Championship": 1
        }
        
        upset_counts = defaultdict(int)
        
        for bracket in self.winning_brackets:
            results = bracket.simulate_tournament()
            
            for round_name, teams in results.items():
                if round_name != "Champion":  # Skip final single-team result
                    expected_max_seed = EXPECTED_MAX_SEEDS[round_name]
                    
                    # Count any team with seed higher than expected as an upset
                    for team in teams:
                        if team.seed > expected_max_seed:
                            key = (round_name, team.seed, team.name)
                            upset_counts[key] += 1
        
        # Convert to DataFrame
        upsets_df = pd.DataFrame([
            {
                'round': round_name,
                'seed': seed,
                'team': team,
                'frequency': count / self.num_pools
            }
            for (round_name, seed, team), count in upset_counts.items()
        ])
        
        if upsets_df.empty:
            return pd.DataFrame(columns=['round', 'seed', 'team', 'frequency'])
        
        # Sort chronologically by round, then by frequency within each round
        upsets_df['round_order'] = upsets_df['round'].map(
            {round_name: i for i, round_name in enumerate(self.ROUND_ORDER)}
        )
        upsets_df = upsets_df.sort_values(
            ['round_order', 'frequency'], 
            ascending=[True, False]
        )
        upsets_df = upsets_df.drop('round_order', axis=1)
        upsets_df.rename(columns={"round":"make_it_to"},inplace=True)
        
        return upsets_df
    
    def analyze_champion_picks(self) -> pd.DataFrame:
        """
        Analyze championship picks in winning brackets
        
        Returns:
            DataFrame containing champion pick statistics
        """
        champion_counts = defaultdict(int)
        
        for bracket in self.winning_brackets:
            results = bracket.simulate_tournament()
            champion = results['Champion']
            key = (champion.seed, champion.name, champion.conference)
            champion_counts[key] += 1
        
        # Convert to DataFrame
        champions_df = pd.DataFrame([
            {
                'seed': seed,
                'team': team,
                'conference': conf,
                'frequency': count / self.num_pools
            }
            for (seed, team, conf), count in champion_counts.items()
        ])
        
        return champions_df.sort_values('frequency', ascending=False)

def main():
    """Example usage of bracket analysis"""
    # Get current standings
    standings = Standings()
    
    # Initialize analyzer
    analyzer = BracketAnalysis(standings, num_pools=1000)
    
    # Run simulations
    analyzer.simulate_pools(entries_per_pool=10)
    
    # Print various analyses
    print("\nUpset Statistics by Round:")
    print(analyzer.analyze_upsets().to_string(index=False))
    
    print("\nMost Common Underdogs:")
    print(analyzer.find_common_underdogs().groupby("make_it_to").head(10).to_string(index=False))
    
    print("\nChampionship Pick Analysis:")
    print(analyzer.analyze_champion_picks().head(10).to_string(index=False))

if __name__ == "__main__":
    main()
