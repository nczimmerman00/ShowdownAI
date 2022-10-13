import logging

from selenium.webdriver.common.by import By
import os
from dotenv import load_dotenv
from selenium.webdriver.common.keys import Keys
import time
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.select import Select


def awaitElement(driver, searchType, element):
    counter = 0
    while True:
        try:
            driver.find_element(searchType, element)
            time.sleep(.1)
            return True
        except NoSuchElementException:
            if counter < 20:
                counter += 1
                time.sleep(1)
            else:
                raise Exception('Await element timed out.\nsearchType: ' + searchType + '\nelement: ' + element)


def login(driver):
    # xpaths
    chooseNameButton = '//*[@id="header"]/div[3]/button[1]'
    usernameTextField = '/html/body/div[4]/div/form/p[1]/label/input'
    usernameSubmitButton = '/html/body/div[4]/div/form/p[2]/button[1]/strong'
    passwordTextField = '/html/body/div[4]/div/form/p[4]/label/input'
    passwordSubmitButton = '/html/body/div[4]/div/form/p[5]/button[1]/strong'
    loggedInButton = '//*[@id="header"]/div[3]/span'
    accountName = '//*[@id="header"]/div[3]/span'

    load_dotenv()

    # Check to see if a login is needed
    try:
        needToLogin = driver.find_element(By.XPATH, chooseNameButton)
    except NoSuchElementException:
        needToLogin = False
    if needToLogin:
        try:
            time.sleep(2)
            awaitElement(driver, By.XPATH, chooseNameButton)
            driver.find_element(By.XPATH, chooseNameButton).click()
            awaitElement(driver, By.XPATH, usernameTextField)
            textFieldEnter = driver.find_element(By.XPATH, usernameTextField)
            textFieldEnter.send_keys(os.getenv("LOGIN_USERNAME"))
            driver.find_element(By.XPATH, usernameSubmitButton).click()
            awaitElement(driver, By.XPATH, passwordTextField)
            textFieldEnter = driver.find_element(By.XPATH, passwordTextField)
            textFieldEnter.send_keys(os.getenv("LOGIN_PASSWORD"))
            driver.find_element(By.XPATH, passwordSubmitButton).click()
            awaitElement(driver, By.XPATH, accountName)
        except BaseException as e:
            print("Failed to login.")
            print(e)
            return False
    elif driver.find_element(By.XPATH, loggedInButton):
        return True
    else:
        return False



def uploadTeam(driver, teamName, format):
    # xpaths
    teambuilderButton = '//*[@id="room-"]/div/div[1]/div[2]/div[2]/p[1]/button'
    newTeamButton = '//*[@id="room-teambuilder"]/div[2]/p[3]/button[1]'
    importFromTextButton = '//*[@id="room-teambuilder"]/div/div/div/ol/li[4]/button'
    teamTextBox = '//*[@id="room-teambuilder"]/div/div[2]/textarea'
    teamNameTextBox = '//*[@id="room-teambuilder"]/div/div[1]/input'
    importButton = '//*[@id="room-teambuilder"]/div/div[1]/button[2]'
    formatSelectMenu = '//*[@id="room-teambuilder"]/div/div/div/ol/li[2]/button[1]'
    formatButton = '/html/body/div[5]/ul[1]/li[' #_]/button
    validateButton = '//*[@id="room-teambuilder"]/div/div/div/ol/li[2]/button[2]'
    validationResult = '/html/body/div[5]/div/form/p[1]'
    validateOkButton = '/html/body/div[5]/div/form/p[2]/button/strong'
    exitTeambuilderButton = '//*[@id="header"]/div[2]/div/ul[1]/li[2]/button'

    formats = {
        'OU': '2', 'Ubers': '3', 'UU': '4',
        'RU': '5', 'NU': '6', 'PU': '7', 'LC': '8'
    }

    try:
        # awaitElement(driver, By.XPATH, teambuilderButton)
        # driver.find_element(By.XPATH, teambuilderButton).click()
        awaitElement(driver, By.XPATH, newTeamButton)
        driver.find_element(By.XPATH, newTeamButton).click()
        awaitElement(driver, By.XPATH, importFromTextButton)
        driver.find_element(By.XPATH, importFromTextButton).click()
    except BaseException as e:
        print("Failed to navigate team builder page.")
        print(e)
        return False

    # Copy pokepaste from text file
    try:
        teamFilePath = os.path.dirname(os.getcwd()) + '/teams/' + teamName + '.txt'
        with open(teamFilePath, 'r') as teamFile:
            teamText = teamFile.read()
    except BaseException as e:
        print("Failed to read team file.")
        print(e)
        return False

    # Paste into teambuilder
    try:
        awaitElement(driver, By.XPATH, teamTextBox)
        textFieldEnter = driver.find_element(By.XPATH, teamTextBox)
        textFieldEnter.send_keys(teamText)
        textFieldEnter = driver.find_element(By.XPATH, teamNameTextBox)
        #textFieldEnter.clear()
        textFieldEnter.send_keys(Keys.CONTROL + "a")
        textFieldEnter.send_keys(teamName)
        driver.find_element(By.XPATH, importButton).click()
        awaitElement(driver, By.XPATH, formatSelectMenu)
        driver.find_element(By.XPATH, formatSelectMenu).click()
        time.sleep(1)
        formatButton += formats[format] + ']/button'
        driver.find_element(By.XPATH, formatButton).click()
        awaitElement(driver, By.XPATH, validateButton)
        driver.find_element(By.XPATH, validateButton).click()
    except BaseException as e:
        print("Failed to upload team.")
        print(e)
        return False

    # Check to see if team is valid for format
    try:
        time.sleep(1)
        validText = 'Your team is valid for '
        validationText = driver.find_element(By.XPATH, validationResult).text
        teamIsValid = validText in validationText
        # Return to home menu
        driver.find_element(By.XPATH, validateOkButton).click()
        awaitElement(driver, By.XPATH, exitTeambuilderButton)
        driver.find_element(By.XPATH, exitTeambuilderButton).click()
        if not teamIsValid:
            print("Invalid team given.")
            return False
    except BaseException as e:
        print("Failed to check team validation.")
        print(e)
        return False

    return True


def selectAvatar(driver):
    # xpaths
    accountName = '//*[@id="header"]/div[3]/span'
    changePFP = '/html/body/div[4]/div/img'
    selectedPFP = '/html/body/div[4]/div/div[1]/button[120]'

    try:
        awaitElement(driver, By.XPATH, accountName)
        driver.find_element(By.XPATH, accountName).click()
    except NoSuchElementException:
        print('Error: Need to login to select avatar.')
        exit()
    awaitElement(driver, By.XPATH, changePFP)
    driver.find_element(By.XPATH, changePFP).click()
    awaitElement(driver, By.XPATH, selectedPFP)
    driver.find_element(By.XPATH, selectedPFP).click()


def enterQueue(driver):
    driver.find_element(By.CLASS_NAME, 'formatselect').click()
    time.sleep(.5)
    format_buttons = driver.find_elements(By.NAME, 'selectFormat')
    format_buttons[0].click()
    time.sleep(.5)
    buttons = driver.find_elements(By.CLASS_NAME, 'big')
    buttons[0].click()


def awaitChallenge(driver):
    waitingForMatch = True
    while waitingForMatch:
        try:
            challenge = driver.find_element(By.CLASS_NAME, 'challenge')
            if challenge.find_element(By.CLASS_NAME, 'formatselect').get_attribute('value') == 'gen8randombattle':
                awaitElement(driver, By.NAME, 'acceptChallenge')
                driver.find_element(By.NAME, 'acceptChallenge').click()
                waitingForMatch = False
            else:
                awaitElement(driver, By.NAME, 'rejectChallenge')
                driver.find_element(By.NAME, 'rejectChallenge').click()
        except NoSuchElementException:
            time.sleep(4)
            continue


def check_elo(driver):
    ladder_button = driver.find_element(By.CLASS_NAME, 'mainmenu3')
    ladder_button.click()
    time.sleep(1)
    element_grab = driver.find_element(By.CLASS_NAME, 'ladder')
    user_lookup = element_grab.find_element(By.TAG_NAME, 'a')
    user_lookup.click()
    time.sleep(2.5)

    # Switch Tabs
    p = driver.current_window_handle
    parent = driver.window_handles[0]
    chld = driver.window_handles[1]
    driver.switch_to.window(chld)

    form = driver.find_element(By.TAG_NAME, 'form')
    text_input = form.find_element(By.CLASS_NAME, 'textbox')
    load_dotenv()
    text_input.send_keys(os.getenv("LOGIN_USERNAME"))
    submit_button = form.find_element(By.TAG_NAME, 'button')
    submit_button.click()
    time.sleep(5)
    table = driver.find_element(By.TAG_NAME, 'table')
    rows = table.find_elements(By.TAG_NAME, 'tr')
    return_value = None
    for row in rows:
        try:
            data = row.find_elements(By.TAG_NAME, 'td')
            if data[0].text == 'gen8randombattle':
                return_value = int(data[1].text)
        except IndexError:
            continue
    # Close browser tab
    driver.switch_to.window(chld)
    driver.close()
    driver.switch_to.window(parent)
    time.sleep(.5)
    # Close ladder tab
    close_button = driver.find_element(By.CLASS_NAME, 'closebutton')
    close_button.click()
    time.sleep(.5)
    if return_value:
        return return_value
    else:
        logging.warning('Elo for gen8randombattle not found, returning 1000.')
        return 1000


def exit_battle(driver):
    close_button = driver.find_element(By.CLASS_NAME, 'closebutton')
    close_button.click()
    time.sleep(1)


def disable_animations(driver):
    button = driver.find_element(By.NAME, 'openOptions')
    button.click()
    time.sleep(.5)
    theme = Select(driver.find_element(By.NAME, 'theme'))
    theme.select_by_visible_text('Dark')
    animations = driver.find_element(By.NAME, 'noanim')
    animations.click()
    time.sleep(.5)
