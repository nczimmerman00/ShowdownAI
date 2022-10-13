import re
import time
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium import webdriver
from webFunctions import awaitElement
from infoScraping import getToolTip
import pandas as pd

while True:
    NUMBER_OF_GAMES = input("Enter number of games to search: ")
    try:
        NUMBER_OF_GAMES = int(NUMBER_OF_GAMES)
        break
    except:
        print("Invalid input. Input must be an integer. Please try again.")

statChanges = {
    '4': 6,
    '3.5': 5,
    '3': 4,
    '2.5': 3,
    '2': 2,
    '1.5': 1,
    '0.67': -1,
    '0.5': -2,
    '0.4': -3,
    '0.33': -4,
    '0.29': -5,
    '0.25': -6
}


class FieldConditions:
    def __init__(self):
        self.weather = 'None'  # 1 = None, 2 = Rain, 3 = Sun, 4 = Sandstorm, 5 = Hail
        self.terrain = 'None'  # 1 = None, 2 = Grassy, 3 = Psychic, 4 = Misty, 5 = Electric
        self.p1ScreenUp = False  # True-False
        self.p2ScreenUp = False  # True-False
        self.p1DamageEntryHazard = False  # True-False
        self.p2DamageEntryHazard = False  # True-False
        self.p1ToxicSpikes = False  # True-False
        self.p2ToxicSpikes = False  # True-False
        self.p1StickyWeb = False  # True-False
        self.p2StickyWeb = False  # True-False


class LeadPokemon:
    def __init__(self):
        self.name = None    # Not submitted to the ai
        self.hp = 100
        self.type1 = 'None'
        self.type2 = 'None'
        self.status = False
        self.atkBoosts = 0
        self.defBoosts = 0
        self.spaBoosts = 0
        self.spdBoosts = 0
        self.speBoosts = 0
        self.isDynamaxed = False
        self.isConfused = False
        self.isLeechSeeded = False
        self.isDrowsy = False
        self.isTaunted = False
        self.isEncored = False


class ReservePokemon:
    def __init__(self):
        self.name = None  # Not submitted to the ai
        self.hp = 100
        self.revealed = False


class OtherValues:
    def __init__(self):
        self.p1PokemonRemaining = 6
        self.p2PokemonRemaining = 6
        self.p1PokemonRevealed = 1
        self.p2PokemonRevealed = 1
        self.p1TeamStatuses = 0
        self.p2TeamStatuses = 0


training_data = pd.read_csv('../battle_ai/training_data.csv')

chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument("--mute-audio")
chrome_options.add_argument("--start-maximized")
url = 'https://replay.pokemonshowdown.com/'
s = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=s, options=chrome_options)
driver.get(url)
time.sleep(1)

format_search_bar = '/html/body/div[2]/div/form[2]/p/label/input'
format_search_button = '/html/body/div[2]/div/form[2]/p/button'
awaitElement(driver, By.XPATH, format_search_bar)
textFieldEnter = driver.find_element(By.XPATH, format_search_bar)
textFieldEnter.send_keys('gen8randombattle')
driver.find_element(By.XPATH, format_search_button).click()
time.sleep(1)

# Find the games to be analyzed
awaitElement(driver, By.CLASS_NAME, 'linklist')
games_element = driver.find_element(By.CLASS_NAME, 'linklist')
games_list = games_element.find_elements(By.TAG_NAME, 'li')
while len(games_list) < NUMBER_OF_GAMES:
    # Find more button and click it
    button_list = driver.find_elements(By.CLASS_NAME, 'button')
    for button in button_list:
        if button.text == 'More':
            button.click()
            time.sleep(1)
            break
    awaitElement(driver, By.CLASS_NAME, 'linklist')
    games_element = driver.find_element(By.CLASS_NAME, 'linklist')
    games_list = games_element.find_elements(By.TAG_NAME, 'li')
time.sleep(.5)

for game_button in games_list:
    link = game_button.find_element(By.TAG_NAME, 'a')
    link.click()
    try:
        awaitElement(driver, By.CLASS_NAME, 'uploaddate')
    except Exception:
        continue

    # Check to make sure game has not already been added to training data
    game_id = driver.current_url[driver.current_url.index('-') + 1:]
    try:
        if game_id in training_data['Match_ID']:
            continue
    except KeyError:
        pass

    # Check if game was ranked, skip if not
    try:
        rating_text = driver.find_element(By.CLASS_NAME, 'uploaddate').text
        if 'Rating' not in rating_text:
            continue
        rating_text = rating_text[-4:]
    except NoSuchElementException:
        continue

    # Scrape info for every turn
    last_turn = False
    first_turn = True
    replay_buttons = driver.find_element(By.CLASS_NAME, 'replay-controls')
    next_turn = replay_buttons.find_element(By.XPATH, '//button[4]')
    time.sleep(.5)

    # Get player names and game win/loss
    searchAborted = False
    player1_name = driver.find_element(By.CLASS_NAME, 'trainer-near').text
    player2_name = driver.find_element(By.CLASS_NAME, 'trainer-far').text
    while not last_turn:
        next_turn = replay_buttons.find_element(By.XPATH, '//button[4]')
        try:
            next_turn.click()
        except ElementClickInterceptedException:
            searchAborted = True
            break
        if not first_turn:
            battle_history = driver.find_elements(By.CLASS_NAME, 'battle-history')
            if ' won the battle!' in battle_history[-1].text:
                name_end_index = battle_history[-1].text.index(' won the battle!')
                winner_name = battle_history[-1].text[:name_end_index]
                if player1_name == winner_name:
                    game_result = 'Win'
                elif player2_name == winner_name:
                    game_result = 'Loss'
                else:
                    raise Exception('Player name not found in the winner announcement message')
                break
        first_turn = False
    if searchAborted:
        continue
    last_turn = False
    time.sleep(.5)
    reset_button = driver.find_element(By.XPATH, '/html/body/div[3]/div/div/div[3]/button[2]')
    reset_button.click()

    # Initialize values
    p1DynamaxAvailable = True
    p2DynamaxAvailable = True
    searchAborted = False
    next_turn = replay_buttons.find_element(By.XPATH, '//button[4]')
    next_turn.click()
    while not last_turn:
        next_turn = replay_buttons.find_element(By.XPATH, '//button[4]')
        next_turn.click()

        # Check to see if it's the last turn of the replay
        battle_history = driver.find_elements(By.CLASS_NAME, 'battle-history')
        if 'won the battle!' in battle_history[-1].text:
            last_turn = True
            continue

        # Re-initialize Values
        field_conditions = FieldConditions()
        p1Lead = LeadPokemon()
        p2Lead = LeadPokemon()
        other_values = OtherValues()
        p1Reserves = []
        for i in range(5):
            p1Reserves.append(ReservePokemon())
        p2Reserves = []
        for i in range(5):
            p2Reserves.append(ReservePokemon())

        # Begin scraping the turn
        # Check for weather or terrain
        hover = ActionChains(driver)
        turn_counter = driver.find_element(By.CLASS_NAME, 'turn')
        hover.move_to_element(turn_counter).perform()
        time.sleep(.1)
        toolTip = getToolTip(driver)
        paragraph_list = toolTip.find_elements(By.TAG_NAME, 'p')
        for p in paragraph_list:
            if 'Rain' in p.text:
                field_conditions.weather = 'Rain'
            elif 'Sun' in p.text:
                field_conditions.weather = 'Sun'
            elif 'Hail' in p.text:
                field_conditions.weather = 'Hail'
            elif 'Sandstorm' in p.text:
                field_conditions.weather = 'Sandstorm'
            if 'Misty Terrain' in p.text:
                field_conditions.terrain = 'Misty Terrain'
            elif 'Electric Terrain' in p.text:
                field_conditions.terrain = 'Electric Terrain'
            elif 'Psychic Terrain' in p.text:
                field_conditions.terrain = 'Psychic Terrain'
            elif 'Grassy Terrain' in p.text:
                field_conditions.terrain = 'Grassy Terrain'

        # Check for entry hazards for both players
        try:
            # Player 1 entry hazards
            hazards = toolTip.find_elements(By.TAG_NAME, 'td')
            hazards_paragraph = hazards[0].find_element(By.TAG_NAME, 'p')
            hazard_text = hazards_paragraph.text
            if 'Stealth Rock' in hazard_text or 'Spikes' in hazard_text:
                field_conditions.p1DamageEntryHazard = True
            if 'Toxic Spikes' in hazard_text:
                field_conditions.p1ToxicSpikes = True
            if 'Sticky Web' in hazard_text:
                field_conditions.p1StickyWeb = True
            if 'Reflect' in hazard_text or 'Light Screen' in hazard_text or 'Aurora Veil' in hazard_text:
                field_conditions.p1ScreenUp = True
            # Player 2 entry hazards
            hazards_paragraph = hazards[1].find_element(By.TAG_NAME, 'p')
            hazard_text = hazards_paragraph.text
            if 'Stealth Rock' in hazard_text or 'Spikes' in hazard_text:
                field_conditions.p2DamageEntryHazard = True
            if 'Toxic Spikes' in hazard_text:
                field_conditions.p2ToxicSpikes = True
            if 'Sticky Web' in hazard_text:
                field_conditions.p2StickyWeb = True
            if 'Reflect' in hazard_text or 'Light Screen' in hazard_text or 'Aurora Veil' in hazard_text:
                field_conditions.p2ScreenUp = True
        except IndexError:
            pass

        # Get Player 1's lead information
        toolTipElements = driver.find_element(By.CLASS_NAME, 'tooltips')
        toolTipElements = toolTipElements.find_elements(By.CLASS_NAME, 'has-tooltip')
        for t in toolTipElements:
            if t.get_attribute('data-id') == 'p1a':
                hover.move_to_element(t).perform()
                time.sleep(.1)
                toolTip = getToolTip(driver)
        # Get lead name for later use
        p1Lead.name = toolTip.find_element(By.TAG_NAME, 'h2').text
        if p1Lead.name == 'Zoroark':
            searchAborted = True
            break
        # HP
        hpText = toolTip.find_elements(By.TAG_NAME, 'p')[0].text
        p1Lead.hp = hpText[hpText.index(':') + 2: hpText.index('%')]
        # Status
        try:
            statusSpan = toolTip.find_element(By.TAG_NAME, 'span')
            p1Lead.status = statusSpan.text
        except NoSuchElementException:
            pass
        # Typing
        typeImages = toolTip.find_elements(By.TAG_NAME, 'img')
        typesFound = 0
        for image in typeImages:
            if 'https://play.pokemonshowdown.com/sprites/types/' in image.get_attribute('src'):
                if typesFound == 0:
                    p1Lead.type1 = image.get_attribute('alt')
                    typesFound += 1
                elif typesFound == 1:
                    p1Lead.type2 = image.get_attribute('alt')
                    break

        # Stat Boosts + Volatile Conditions
        healthBar = driver.find_element(By.CLASS_NAME, 'rstatbar')
        statusList = healthBar.find_element(By.CLASS_NAME, 'status')
        statusList = statusList.find_elements(By.TAG_NAME, 'span')
        for status in statusList:
            # Make sure status condition is not added to the volatile condition list
            if status.text == p1Lead.status:
                continue
            # Check if status is a stat change
            if re.search(r'[0-4](\.\d\d?)?×', status.text):
                # Get the stat boost stage from the element text
                try:
                    statModifier = statChanges[re.search(r'[0-4](\.\d\d?)?', status.text).group()]
                except KeyError:
                    continue
                statText = status.text[-3:]
                if statText == 'Atk':
                    p1Lead.atkBoosts = statModifier
                elif statText == 'Def':
                    p1Lead.defBoosts = statModifier
                elif statText == 'SpA':
                    p1Lead.spaBoosts = statModifier
                elif statText == 'SpD':
                    p1Lead.spdBoosts = statModifier
                elif statText == 'Spe':
                    p1Lead.speBoosts = statModifier
            elif status.text == 'Dynamaxed':
                p1Lead.isDynamaxed = True
                p1DynamaxAvailable = False
            elif status.text == 'Confused':
                p1Lead.isConfused = True
            elif status.text == 'Encore':
                p1Lead.isEncored = True
            elif status.text == 'Leech Seed':
                p1Lead.isLeechSeeded = True
            elif status.text == 'Drowsy':
                p1Lead.isConfused = True
            elif status.text == 'Taunt':
                p1Lead.isTaunted = True

        # Get Player 1's benched pokemon
        reserveIndex = 0
        iconRows = driver.find_element(By.CLASS_NAME, 'leftbar')
        iconRows = iconRows.find_element(By.CLASS_NAME, 'trainer')
        iconRows = iconRows.find_elements(By.CLASS_NAME, 'teamicons')
        if len(iconRows) > 3:
            searchAborted = True
            break
        for row in iconRows:
            icons = row.find_elements(By.CLASS_NAME, 'has-tooltip')
            for icon in icons:
                if reserveIndex > 4:
                    continue
                hover.move_to_element(icon).perform()
                time.sleep(.1)
                toolTip = getToolTip(driver)
                p1Reserves[reserveIndex].name = toolTip.find_element(By.TAG_NAME, 'h2').text
                if p1Reserves[reserveIndex].name == p1Lead.name:
                    continue
                other_values.p1PokemonRevealed += 1
                p1Reserves[reserveIndex].revealed = True
                # HP
                hpText = toolTip.find_elements(By.TAG_NAME, 'p')[0].text
                if '(fainted)' in hpText:
                    p1Reserves[reserveIndex].hp = 0
                    other_values.p1PokemonRemaining -= 1
                else:
                    p1Reserves[reserveIndex].hp = hpText[hpText.index(':') + 2:hpText.index('%')]
                # Status
                try:
                    statusSpan = toolTip.find_element(By.TAG_NAME, 'span')
                    other_values.p1TeamStatuses += 1
                except NoSuchElementException:
                    pass
                reserveIndex += 1

        # Get Player 2's lead information
        toolTipElements = driver.find_element(By.CLASS_NAME, 'tooltips')
        toolTipElements = toolTipElements.find_elements(By.CLASS_NAME, 'has-tooltip')
        for t in toolTipElements:
            if t.get_attribute('data-id') == 'p2a':
                hover.move_to_element(t).perform()
                time.sleep(.1)
                toolTip = getToolTip(driver)
        # Get lead name for later use
        p2Lead.name = toolTip.find_element(By.TAG_NAME, 'h2').text
        if p2Lead.name == 'Zoroark':
            searchAborted = True
            break
        # HP
        hpText = toolTip.find_elements(By.TAG_NAME, 'p')[0].text
        p2Lead.hp = hpText[hpText.index(':') + 2: hpText.index('%')]
        # Status
        try:
            statusSpan = toolTip.find_element(By.TAG_NAME, 'span')
            p2Lead.status = statusSpan.text
        except NoSuchElementException:
            pass
        # Typing
        typeImages = toolTip.find_elements(By.TAG_NAME, 'img')
        typesFound = 0
        for image in typeImages:
            if 'https://play.pokemonshowdown.com/sprites/types/' in image.get_attribute('src'):
                if typesFound == 0:
                    p2Lead.type1 = image.get_attribute('alt')
                    typesFound += 1
                elif typesFound == 1:
                    p2Lead.type2 = image.get_attribute('alt')
                    break

        # Stat Boosts + Volatile Conditions
        healthBar = driver.find_element(By.CLASS_NAME, 'lstatbar')
        statusList = healthBar.find_element(By.CLASS_NAME, 'status')
        statusList = statusList.find_elements(By.TAG_NAME, 'span')
        for status in statusList:
            # Make sure status condition is not added to the volatile condition list
            if status.text == p2Lead.status:
                continue
            # Check if status is a stat change
            if re.search(r'[0-4](\.\d\d?)?×', status.text):
                # Get the stat boost stage from the element text
                try:
                    statModifier = statChanges[re.search(r'[0-4](\.\d\d?)?', status.text).group()]
                except KeyError:
                    continue
                statText = status.text[-3:]
                if statText == 'Atk':
                    p2Lead.atkBoosts = statModifier
                elif statText == 'Def':
                    p2Lead.defBoosts = statModifier
                elif statText == 'SpA':
                    p2Lead.spaBoosts = statModifier
                elif statText == 'SpD':
                    p2Lead.spdBoosts = statModifier
                elif statText == 'Spe':
                    p2Lead.speBoosts = statModifier
            elif status.text == 'Dynamaxed':
                p2Lead.isDynamaxed = True
                p2DynamaxAvailable = False
            elif status.text == 'Confused':
                p2Lead.isConfused = True
            elif status.text == 'Encore':
                p2Lead.isEncored = True
            elif status.text == 'Leech Seed':
                p2Lead.isLeechSeeded = True
            elif status.text == 'Drowsy':
                p2Lead.isConfused = True
            elif status.text == 'Taunt':
                p2Lead.isTaunted = True

        # Get Player 1's benched pokemon
        reserveIndex = 0
        iconRows = driver.find_element(By.CLASS_NAME, 'rightbar')
        iconRows = iconRows.find_element(By.CLASS_NAME, 'trainer')
        iconRows = iconRows.find_elements(By.CLASS_NAME, 'teamicons')
        if len(iconRows) > 3:
            searchAborted = True
            break
        for row in iconRows:
            icons = row.find_elements(By.CLASS_NAME, 'has-tooltip')
            for icon in icons:
                if reserveIndex > 4:
                    continue
                hover.move_to_element(icon).perform()
                time.sleep(.1)
                toolTip = getToolTip(driver)
                p2Reserves[reserveIndex].name = toolTip.find_element(By.TAG_NAME, 'h2').text
                if p2Reserves[reserveIndex].name == p2Lead.name:
                    continue
                other_values.p2PokemonRevealed += 1
                p2Reserves[reserveIndex].revealed = True
                # HP
                hpText = toolTip.find_elements(By.TAG_NAME, 'p')[0].text
                if '(fainted)' in hpText:
                    p2Reserves[reserveIndex].hp = 0
                    other_values.p2PokemonRemaining -= 1
                else:
                    p2Reserves[reserveIndex].hp = hpText[hpText.index(':') + 2: hpText.index('%')]
                # Status
                try:
                    statusSpan = toolTip.find_element(By.TAG_NAME, 'span')
                    other_values.p2TeamStatuses += 1
                except NoSuchElementException:
                    pass
                reserveIndex += 1

        # Input turn info to training_data.csv
        turn_values = {
            'Match_ID': game_id, 'WinOrLoss': game_result, 'Elo': rating_text,
            'Weather': field_conditions.weather, 'Terrain': field_conditions.terrain,
            'P1ScreenUp': field_conditions.p1ScreenUp, 'P2ScreenUp': field_conditions.p2ScreenUp,
            'P1HasDamageEntryHazards': field_conditions.p1DamageEntryHazard,
            'P2HasDamageEntryHazards': field_conditions.p2DamageEntryHazard,
            'P1HasToxicSpikes': field_conditions.p1ToxicSpikes, 'P2HasToxicSpikes': field_conditions.p2ToxicSpikes,
            'P1HasStickyWeb': field_conditions.p1StickyWeb, 'P2HasStickyWeb': field_conditions.p2StickyWeb,
            'P1PokemonRemaining': other_values.p1PokemonRemaining, 'P2PokemonRemaining': other_values.p2PokemonRemaining,
            'P1PokemonRevealed': other_values.p1PokemonRevealed, 'P2PokemonRevealed': other_values.p2PokemonRevealed,
            'P1TeamStatuses': other_values.p1TeamStatuses, 'P2TeamStatuses': other_values.p2TeamStatuses,
            'P1DynamaxAvailable': p1DynamaxAvailable, 'P2DynamaxAvailable': p2DynamaxAvailable,
            'P1LeadHP': p1Lead.hp, 'P1LeadType1': p1Lead.type1, 'P1LeadType2': p1Lead.type2, 'P1LeadStatus': p1Lead.status,
            'P1AtkBoosts': p1Lead.atkBoosts, 'P1DefBoosts': p1Lead.defBoosts, 'P1SpaBoosts': p1Lead.spaBoosts,
            'P1SpdBoosts': p1Lead.spdBoosts, 'P1SpeBoosts': p1Lead.speBoosts,
            'P1LeadDynamaxed': p1Lead.isDynamaxed, 'P1LeadConfused': p1Lead.isConfused,
            'P1LeadLeechSeed': p1Lead.isLeechSeeded, 'P1LeadDrowsy': p1Lead.isDrowsy,
            'P1LeadTaunted': p1Lead.isTaunted, 'P1LeadEncore': p1Lead.isEncored,
            'P1R1HP': p1Reserves[0].hp, 'P1R1Revealed': p1Reserves[0].revealed,
            'P1R2HP': p1Reserves[1].hp, 'P1R2Revealed': p1Reserves[1].revealed,
            'P1R3HP': p1Reserves[2].hp, 'P1R3Revealed': p1Reserves[2].revealed,
            'P1R4HP': p1Reserves[3].hp, 'P1R4Revealed': p1Reserves[3].revealed,
            'P1R5HP': p1Reserves[4].hp, 'P1R5Revealed': p1Reserves[4].revealed,
            'P2LeadHP': p2Lead.hp, 'P2LeadType1': p2Lead.type1, 'P2LeadType2': p2Lead.type2, 'P2LeadStatus': p2Lead.status,
            'P2AtkBoosts': p2Lead.atkBoosts, 'P2DefBoosts': p2Lead.defBoosts, 'P2SpaBoosts': p2Lead.spaBoosts,
            'P2SpdBoosts': p2Lead.spdBoosts, 'P2SpeBoosts': p2Lead.speBoosts,
            'P2LeadDynamaxed': p2Lead.isDynamaxed, 'P2LeadConfused': p2Lead.isConfused,
            'P2LeadLeechSeed': p2Lead.isLeechSeeded, 'P2LeadDrowsy': p2Lead.isDrowsy,
            'P2LeadTaunted': p2Lead.isTaunted, 'P2LeadEncore': p2Lead.isEncored,
            'P2R1HP': p2Reserves[0].hp, 'P2R1Revealed': p2Reserves[0].revealed,
            'P2R2HP': p2Reserves[1].hp, 'P2R2Revealed': p2Reserves[1].revealed,
            'P2R3HP': p2Reserves[2].hp, 'P2R3Revealed': p2Reserves[2].revealed,
            'P2R4HP': p2Reserves[3].hp, 'P2R4Revealed': p2Reserves[3].revealed,
            'P2R5HP': p2Reserves[4].hp, 'P2R5Revealed': p2Reserves[4].revealed
        }
        new_series = pd.Series(list(turn_values.values()), index=list(turn_values.keys()))
        training_data = pd.concat([training_data, new_series.to_frame().T], ignore_index=True)
        training_data.to_csv('../battle_ai/training_data.csv', index=False)
exit()
