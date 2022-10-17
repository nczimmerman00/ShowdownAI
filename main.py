import asyncio
import logging
import os
import pickle
import time
#import webInterface.battleControls as battleControls
#import webInterface.webFunctions as webFunctions
#import webInterface.infoScraping as infoScraping
import webInterface
#from simulation.calculations import OutcomeNode, decide_option
from simulation import OutcomeNode, decide_option
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium import webdriver
import traceback
from tensorflow import keras
from pickle import load
#from statistics import save_results
from simulation import save_results
from dotenv import load_dotenv


TURN_DEPTH = 1
MODEL_NAME = 'model2'
MODE = 'CHALLENGE'     # Set to 'LADDER' or 'CHALLENGE'


async def main():
    load_dotenv('webInterface/.env')
    USER_NAME = os.getenv("LOGIN_USERNAME")
    with open('log.txt', 'w'):
        pass
    logging.basicConfig(filename='log.txt', encoding='utf-8', level=logging.INFO)
    if MODEL_NAME in ['model1', 'model2']:
        path = os.path.dirname(__file__) + '/battle_ai/models/' + MODEL_NAME + '.h5'
        model = keras.models.load_model(path)
        prediction_function = model.predict
    else:
        with open('battle_ai/models/' + MODEL_NAME + '.pkl', 'rb') as file:
            model = pickle.load(file)
            prediction_function = model.predict_proba
    scalar = load(open('battle_ai/models/scalar.pkl', 'rb'))

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--mute-audio")
    chrome_options.add_argument("--start-maximized")
    url = 'https://play.pokemonshowdown.com'
    s = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=s, options=chrome_options)
    driver.get(url)

    webInterface.updatePossibleSets()
    webInterface.login(driver)
    webInterface.selectAvatar(driver)
    webInterface.disable_animations(driver)

    # Queue Loop
    while True:
        # Grab current elo
        try:
            current_elo = webInterface.check_elo(driver)
        except Exception:
            current_elo = 1000
        if MODE == 'CHALLENGE':
            webInterface.awaitChallenge(driver)
        elif MODE == 'LADDER':
            webInterface.enterQueue(driver)
        else:
            raise Exception('Invalid MODE entered. (Either enter LADDER or CHALLENGE)')
        currentBattleState = None
        # Game Loop
        while True:
            try:
                battle_finished = webInterface.awaitTurn(driver)
                if battle_finished:
                    break
                if webInterface.check_for_multi_turn_moves(driver):
                    continue
                currentBattleState = await webInterface.getBattleState(driver, currentBattleState, current_elo, USER_NAME)
                decision_list = decide_option(OutcomeNode(currentBattleState, 1, 'Root'), TURN_DEPTH, prediction_function, scalar)
                # Select best option from decision list. If False is returned, try next best option.
                option_selected = False
                for i in range(len(decision_list)):
                    option_selected = webInterface.select_option(driver, decision_list[i])
                    if option_selected:
                        # If selected option was an attack, set lastUsedMove on my lead
                        if decision_list[i].mySelectedOption[0] is not None:
                            currentBattleState.myTeam[currentBattleState.myLeadIndex].lastUsedMove = \
                                decision_list[i].mySelectedOption[0].name
                        break
                if not option_selected:
                    logging.critical('Option selection failed! Switching to random select.')
                    option_selected = webInterface.random_select(driver)
                    if option_selected:
                        continue
                    else:
                        logging.critical('Random selection failed! Ending game.')
                        webInterface.surrender(driver)
                        break
            except Exception as e:
                if webInterface.checkBattleCompletion(driver):
                    continue
                logging.critical(traceback.format_exc())
                exit()
        # Record results
        opponent_name = currentBattleState.opponentName
        elo = currentBattleState.elo
        try:
            result = webInterface.find_winner(driver, USER_NAME)
            webInterface.exit_battle(driver)
        except:
            result = False
        save_results(MODEL_NAME, opponent_name, elo, result)

        time.sleep(15)
    driver.close()
    exit()

asyncio.run(main())
