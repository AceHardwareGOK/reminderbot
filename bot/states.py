from enum import Enum

class ConversationState(Enum):
    """States for conversation flow"""
    CHOOSING_ACTION = 0
    DESCRIBING_TASK = 1
    CHOOSING_DAYS = 2
    CHOOSING_TIMES = 3
    CHOOSING_INTERVAL = 4
    VIEWING_TASKS = 5
    CHOOSING_ONE_TIME_DATE = 6
    # Edit states
    EDIT_SELECT_FIELD = 7
    EDIT_ENTER_VALUE = 8
    EDIT_CHOOSING_DAYS = 9
    EDIT_CHOOSING_ONE_TIME_DATE = 10

