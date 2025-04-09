from queue import Queue

# Create a global queue for analysis jobs
analysis_queue = Queue()

# Add any queue-related utility functions here if needed
def get_queue_size() -> int:
    """Get the current size of the analysis queue"""
    return analysis_queue.qsize() 
