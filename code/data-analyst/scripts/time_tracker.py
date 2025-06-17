import time
import boto3
import os
from typing import Dict
from datetime import datetime

class ProcessingTimeTracker:
    def __init__(self):
        self.s3_client = boto3.client('s3')
        self.times: Dict[str, Dict[str, float]] = {}
        self.current_process = None
        self.start_time = None
        self.bucket_name = os.environ.get('S3_BUCKET_NAME')

    def start_process(self, iteration_id: str, process_name: str):
        """Start timing a process"""
        if iteration_id not in self.times:
            self.times[iteration_id] = {}
        
        self.current_process = process_name
        self.start_time = time.time()

    def end_process(self, iteration_id: str):
        """End timing the current process"""
        if self.start_time and self.current_process:
            duration = time.time() - self.start_time
            self.times[iteration_id][self.current_process] = duration
            self.start_time = None
            self.current_process = None

    def save_times(self, iteration_id: str, query: str = None):
        """Save the timing results to S3"""
        try:
            if iteration_id in self.times:
                current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = f"processing_times/{iteration_id}_{current_time}.txt"
                
                # Format the output
                display_id = query if query else iteration_id
                output = f"Processing times for iteration: {display_id}\n"
                output += f"Timestamp: {datetime.now()}\n\n"
                
                for process, duration in self.times[iteration_id].items():
                    output += f"{process}: {duration:.3f} seconds\n"
                
                # Calculate and add total time
                total_time = sum(self.times[iteration_id].values())
                output += f"\nTotal processing time: {total_time:.3f} seconds"

                # Save to S3
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=filepath,
                    Body=output
                )
                
                # Clear the times for this iteration
                del self.times[iteration_id]
                
                return total_time
                
        except Exception as e:
            print(f"Error saving processing times: {str(e)}")
            return None
