from datetime import datetime, timedelta
from typing import Tuple, List, Optional

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
    
    @staticmethod
    def parse_date(text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Parse single user date string (e.g. DD.MM.YYYY, DD.MM, YYYY-MM-DD, 'завтра', 'сьогодні')
        optionally with time (HH:MM).
        Returns Tuple[date_iso_str, optional_time_str].
        """
        text = text.strip()
        if not text:
            return None, None
            
        now = datetime.now()
        parts = text.split()
        
        time_part = None
        date_part = parts[0]
        
        if len(parts) >= 2 and Validator.validate_time(parts[1]):
            time_part = parts[1]
        elif len(parts) >= 2 and Validator.validate_time(parts[0]):
            time_part = parts[0]
            date_part = parts[1]
            
        date_lower = date_part.lower()
        if date_lower in ('сьогодні', 'today'):
            return now.strftime('%Y-%m-%d'), time_part
        elif date_lower in ('завтра', 'tomorrow'):
            target_dt = now + timedelta(days=1)
            return target_dt.strftime('%Y-%m-%d'), time_part

        formats = [
            '%d.%m.%Y %H:%M',
            '%d.%m.%Y',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d',
            '%d.%m'
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(text, fmt)
                if fmt == '%d.%m':
                    dt = dt.replace(year=now.year)
                    if dt.date() < now.date():
                        dt = dt.replace(year=now.year + 1)
                
                date_str = dt.strftime('%Y-%m-%d')
                if fmt.endswith('%H:%M'):
                    time_str = dt.strftime('%H:%M')
                    return date_str, time_str
                return date_str, time_part
            except ValueError:
                continue

        return None, None

    @staticmethod
    def parse_dates(text: str) -> Tuple[List[str], Optional[str]]:
        """
        Parse comma-separated date strings.
        Returns Tuple[List[iso_date_strings], optional_time_str].
        Examples:
          "25.07.2026, 28.07.2026" -> (["2026-07-25", "2026-07-28"], None)
          "25.07.2026, 28.07.2026 14:30" -> (["2026-07-25", "2026-07-28"], "14:30")
        """
        text = text.strip()
        if not text:
            return [], None
            
        raw_parts = [p.strip() for p in text.split(',') if p.strip()]
        valid_dates = []
        common_time = None
        
        for part in raw_parts:
            d_str, t_str = Validator.parse_date(part)
            if d_str and d_str not in valid_dates:
                valid_dates.append(d_str)
            if t_str and not common_time:
                common_time = t_str
                
        return valid_dates, common_time
