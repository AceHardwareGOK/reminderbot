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
        """Validate interval is within acceptable range (0 means no repeat)"""
        return 0 <= interval <= 1440
    
    @staticmethod
    def parse_interval(text: str) -> int | None:
        """Parse interval string into minutes (handles plain numbers or HH:MM format)"""
        text = text.strip()
        if ':' in text:
            parts = text.split(':')
            if len(parts) == 2:
                try:
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    if hours >= 0 and minutes >= 0:
                        return hours * 60 + minutes
                except ValueError:
                    return None
            return None
        
        try:
            return int(text)
        except ValueError:
            return None
    
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
