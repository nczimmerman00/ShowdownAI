import csv
import logging
from datetime import datetime
from os.path import exists


def save_results(model_name, opponent_name, elo, result):
    # Check if results file exists
    if not exists('simulation/results.csv'):
        create_save_file()
    with open('simulation/results.csv', 'a', encoding='UTF8') as f:
        writer = csv.writer(f)
        timestamp = datetime.now().strftime('%m/%d/%Y, %H:%M')
        writer.writerow([model_name, timestamp, opponent_name, elo, result])
        logging.info('Results entered!')


def create_save_file():
    headers = ['Model', 'Time', 'Opponent', 'Elo', 'Result']
    with open('simulation/results.csv', 'w', encoding='UTF8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
