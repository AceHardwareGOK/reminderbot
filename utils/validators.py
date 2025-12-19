from datetime import datetime
from typing import Tuple, List

class Validator:
    """Input validation utilities"""
    
    @staticmethod
    def validate_time(time_str: str) -> bool:
        """Validate time format HH:MM"""
        try:
            datetime.strptime(time_str, '%H:%M')
            return True
        except ValueError:
            return False
    
    @staticmethod
    def validate_interval(interval: int) -> bool:
        """Validate interval is within acceptable range"""
        return 1 <= interval <= 1440
    
    @staticmethod
    def parse_times(times_str: str) -> Tuple[List[str], List[str]]:
        """Parse and validate multiple times"""
        times = [t.strip() for t in times_str.split(',')]
        valid_times = []
        invalid_times = []
        
        for t in times:
            if Validator.validate_time(t):
                valid_times.append(t)
            else:
                invalid_times.append(t)
        
        return valid_times, invalid_times
