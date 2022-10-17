import logging
import random
import time
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException
from selenium.webdriver.common.by import By
#from webInterface import adjust_name
import webInterface


# Slot number must be 0-5 inclusive
def chooseTeamPreview(driver, slotNumber):
    try:
        switchOptions = driver.find_elements_by_name("chooseTeamPreview")
    except NoSuchElementException:
        print("Team preview switch options not found.")
        return False
    try:
        for option in switchOptions:
            if option.get_attribute('value') == str(slotNumber):
                option.click()
                break
    except BaseException as e:
        print(e)
        print('Unable to select team preview switch option.')
        return False
    return True


# Slot number must be 1-5 inclusive
def switch(driver, slotNumber):
    available = False
    try:
        switchOptions = driver.find_elements_by_name("chooseSwitch")
    except NoSuchElementException:
        print("No switch options found.")
        return False
    try:
        for option in switchOptions:
            if option.get_attribute('value') == str(slotNumber):
                option.click()
                available = True
                break
        if not available:
            print(option.text + ' could not be selected for a switch.')
            return False
    except BaseException as e:
        print(e)
        print('Unable to select a switch option.')
        return False
    return True


# Slot number must be 1-4 inclusive
def attack(driver, slotNumber):
    try:
        attackOptions = driver.find_elements_by_name('chooseMove')
    except NoSuchElementException:
        print("Team preview switch options not found.")
        return False
    available = False
    try:
        for option in attackOptions:
            if option.get_attribute('value') == str(slotNumber):
                option.click()
                available = True
                break
        if not available:
            print(option.get_attribute('data-move') + ' could not be selected.')
            return False
    except BaseException as e:
        print(e)
        print('Unable to select an attack option.')
        return False
    return True


# Returns True if timer is started
def startTimer(driver):
    # Check if timer is already started
    try:
        driver.find_element(By.CLASS_NAME, 'timerbutton-on')
        return True
    except NoSuchElementException:
        pass
    try:
        button = driver.find_element(By.NAME, 'openTimer')
        button.click()
        time.sleep(.25)
        timerStart = driver.find_element(By.NAME, 'timerOn')
        timerStart.click()
    except NoSuchElementException:
        pass
    except ElementClickInterceptedException:
        pass
    return True


# Returns false if action is need for the turn, true if the battle is finished.
def awaitTurn(driver):
    timer_counter = 0
    timer_started = False
    while True:
        try:
            driver.find_element(By.CLASS_NAME, 'whatdo')
            return False
        except NoSuchElementException:
            try:
                if (checkBattleCompletion(driver)):
                    return True
                else:
                    if timer_counter > 23 and (not timer_started):
                        startTimer(driver)
                        timer_started = True
                    timer_counter += 1
                    time.sleep(5)
                    continue
            except NoSuchElementException:
                continue


# Returns true and closes battle tab if the battle has concluded.
def checkBattleCompletion(driver):
    try:
        driver.find_element(By.NAME, 'closeAndMainMenu')
        print('Battle Finished!')
        return True
    except NoSuchElementException:
        return False


# Returns true if I won the match, False otherwise
def find_winner(driver, username):
    battle_history = driver.find_elements(By.CLASS_NAME, 'battle-history')
    if username in battle_history[-1].text:
        return True
    else:
        return False


def exit_match(driver):
    exit_button = driver.find_element(By.NAME, 'closeAndMainMenu')
    exit_button.click()


# Returns True if attacking is an available option, False otherwise
def check_for_forced_switch(driver):
    try:
        driver.find_element(By.CLASS_NAME, 'movemenu')
        return True
    except NoSuchElementException:
        return False


# Returns True if successful, returns False otherwise
def select_option(driver, outcome):
    if not outcome:
        logging.critical('No outcome given!')
        return False
    if outcome.mySelectedOption is None:
        logging.warning('None found on mySelectedOption')
        return False

    # Get turn number
    turn = driver.find_element(By.CLASS_NAME, 'turn').text

    # Check if selected option is a move or a switch
    if outcome.mySelectedOption[0] is not None:
        # Selected option is an attack
        logging.info('Attempting to use move ' + outcome.mySelectedOption[0].name + ' with ' +
                     outcome.battleState.myTeam[outcome.battleState.myLeadIndex].name)
        option = outcome.mySelectedOption[0]
        if 'max-' in option.name and option.name is not 'dynamax-cannon':
            try:
                dynamax_box = driver.find_element(By.NAME, 'dynamax').click()
                time.sleep(.5)
                elementGrab = driver.find_element(By.CLASS_NAME, 'movebuttons-max')
            except NoSuchElementException:
                elementGrab = driver.find_element(By.CLASS_NAME, 'movemenu')

            buttons = elementGrab.find_elements(By.TAG_NAME, 'button')
        else:
            try:
                elementGrab = driver.find_element(By.CLASS_NAME, 'movebuttons-nomax')
            except NoSuchElementException:
                try:
                    elementGrab = driver.find_element(By.CLASS_NAME, 'movemenu')
                except NoSuchElementException:
                    return False
            buttons = elementGrab.find_elements(By.TAG_NAME, 'button')
        for button in buttons:
            button_text = button.text[:button.text.index('\n')]
            if webInterface.adjust_name(button_text) in option.name:
                button.click()
                time.sleep(1)
                result = check_if_option_was_selected(driver, turn)
                if not result:
                    logging.warning("Couldn't use the move " + option.name)
                    if 'max-' in option.name:
                        dynamax_box = driver.find_element(By.NAME, 'dynamax').click()
                        time.sleep(.5)
                return result
        logging.warning(option.name + ' not found!')
        if 'max-' in option.name:
            try:
                dynamax_box = driver.find_element(By.NAME, 'dynamax').click()
            except NoSuchElementException:
                pass
            time.sleep(.5)
        return False
    else:
        # Selected option is a switch
        logging.info('Attempting to switch to ' + outcome.battleState.myTeam[outcome.mySelectedOption[1]].name)
        elementGrab = driver.find_element(By.CLASS_NAME, 'switchmenu')
        buttons = elementGrab.find_elements(By.TAG_NAME, 'button')
        target_name = outcome.battleState.myTeam[outcome.mySelectedOption[1]].name
        for button in buttons:
            if button.text and button.text in target_name:
                button.click()
                time.sleep(1)
                result = check_if_option_was_selected(driver, turn)
                if not result:
                    logging.warning('Switch to ' + outcome.battleState.myTeam[outcome.mySelectedOption[1]].name +
                                    ' failed!')
                return result
        logging.warning('Switch button for ' + target_name + ' not found!')
        return False


# Selects random move in case of error. Returns True if successful, False otherwise
def random_select(driver):
    attack_options = 0
    switch_options = 0
    awaitTurn(driver)
    # Get number of attack buttons
    try:
        elementGrab = driver.find_element(By.CLASS_NAME, 'movebuttons-nomax')
        buttons = elementGrab.find_elements(By.TAG_NAME, 'button')
        attack_options += len(buttons)
    except NoSuchElementException:
        try:
            elementGrab = driver.find_element(By.CLASS_NAME, 'movemenu')
            buttons = elementGrab.find_elements(By.TAG_NAME, 'button')
            attack_options += len(buttons)
        except NoSuchElementException:
            pass

    # Get number of switch buttons
    menu = driver.find_element(By.CLASS_NAME, 'switchmenu')
    try:
        buttons = menu.find_elements(By.NAME, 'chooseSwitch')
        switch_options += len(buttons)
    except NoSuchElementException:
        pass

    # Get turn number
    turn = driver.find_element(By.CLASS_NAME, 'turn').text

    possible_options = []
    for i in range(attack_options):
        possible_options.append(i)
    for i in range(switch_options):
        possible_options.append(i + 4)
    random.shuffle(possible_options)

    while possible_options:
        random_number = random.randrange(0, len(possible_options), 1)
        random_number = possible_options[random_number]
        # If the random option is an attack
        if random_number < 4:
            try:
                elementGrab = driver.find_element(By.CLASS_NAME, 'movebuttons-nomax')
                buttons = elementGrab.find_elements(By.TAG_NAME, 'button')
                buttons[random_number].click()
            except NoSuchElementException:
                try:
                    elementGrab = driver.find_element(By.CLASS_NAME, 'movemenu')
                    buttons = elementGrab.find_elements(By.TAG_NAME, 'button')
                    buttons[random_number].click()
                except NoSuchElementException:
                    pass
                except ElementClickInterceptedException:
                    pass
            except ElementClickInterceptedException:
                pass
        # If the random option is a switch
        else:
            try:
                menu = driver.find_element(By.CLASS_NAME, 'switchmenu')
                buttons = menu.find_elements(By.NAME, 'chooseSwitch')
                buttons[random_number - 4].click()
            except NoSuchElementException:
                pass
            except ElementClickInterceptedException:
                pass
        possible_options.remove(random_number)
        # Check if button press worked
        time.sleep(1)
        result = check_if_option_was_selected(driver, turn)
        if result:
            return True
    return False


# Returns true if option selected went through, False otherwise
def check_if_option_was_selected(driver, turn_text):
    new_turn = driver.find_element(By.CLASS_NAME, 'turn').text
    # If the opponent hasn't selected an option yet
    try:
        driver.find_element(By.NAME, 'undoChoice')
        return True
    except NoSuchElementException:
        pass
    # If the opponent has selected an option
    try:
        driver.find_element(By.CLASS_NAME, 'switchmenu')
        try:
            driver.find_element(By.CLASS_NAME, 'movemenu')
        except NoSuchElementException:
            return True
    except NoSuchElementException:
        return True
    if turn_text != new_turn:
        return True
    return False


def surrender(driver):
    close_button = driver.find_element(By.CLASS_NAME, 'closebutton')
    close_button.click()
    time.sleep(.5)
    form = driver.find_element(By.TAG_NAME, 'form')
    time.sleep(.5)
    buttons = form.find_elements(By.TAG_NAME, 'button')
    for button in buttons:
        if button.get_attribute("type") == 'submit':
            button.click()


def check_for_multi_turn_moves(driver):
    try:
        moves = driver.find_element(By.CLASS_NAME, 'movemenu')
        buttons = moves.find_elements(By.TAG_NAME, 'button')
        if len(buttons) < 4:
            buttons[0].click()
            return True
    except NoSuchElementException:
        pass
    return False
