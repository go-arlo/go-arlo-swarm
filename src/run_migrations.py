#!/usr/bin/env python
"""
Script to run database migrations for the Go Arlo application.
This script adds the captain_summary column to the analyses table if it doesn't exist.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

parent_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(parent_dir)

print(f"Running migrations from {parent_dir}")
print(f"Python path: {sys.path}")

from go_arlo_agency.database.migrations import main

if __name__ == "__main__":
    main() 
