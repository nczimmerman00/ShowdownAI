import json
import logging
import math
import re
import time
import asyncio
from copy import deepcopy

import aiopoke
import requests
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from webFunctions import awaitElement


class Pokemon:
    def __init__(self):
        self.lookupPerformed = False
        self.name = None
        self.level = -1
        self.hp = 100  # As %
        self.type = []
        self.ability = None
        self.weight = 0
        self.leveledStats = {
            'HP': None,
            'Atk': None,
            'Def': None,
            'Spa': None,
            'SpD': None,
            'Spe': None
        }
        self.effectiveStats = {
            'HP': None,
            'Atk': None,
            'Def': None,
            'Spa': None,
            'SpD': None,
            'Spe': None
        }
        self.fainted = False
        self.inBattle = False
        self.item = []
        self.statusCondition = None  # Brn, Psn, Tox, Par, Slp, Frz
        self.sleepTurns = None
        self.nextToxicDamage = None
        self.volatileConditions = []  # Confusion, Drowsy, Encore, Infatuation, Taunt
        self.confusionTurns = 0
        self.boosts = {
            'Atk': 0,
            'Def': 0,
            'Spa': 0,
            'SpD': 0,
            'Spe': 0,
            'Acc': 0,
            'Eva': 0
        }
        self.substituteHP = 0
        self.isRevealed = False
        self.knownMoveNames = []
        self.knownMoves = []
        self.possibleMoves = []
        self.maxMoves = []
        self.lastUsedMove = None
        self.isDynamaxed = False
        self.turnsDynamaxed = 0
        self.recharging = False
        self.hasMoved = False
        self.isProtected = False
        self.flinched = False
        self.lastDamageTaken = 0

    def __deepcopy__(self, memodict={}):
        cls = self.__class__
        result = cls.__new__(cls)
        memodict[id(self)] = result
        for k, v in self.__dict__.items():
            if k in ['knownMoveNames', 'knownMoves', 'possibleMoves', 'maxMoves', 'lastUsedMove', 'type']:
                setattr(result, k, v)
            else:
                setattr(result, k, deepcopy(v, memodict))
        return result

    def heal(self, health):
        currentHp = self.effectiveStats['HP'] * (self.hp * .01)
        currentHp += health
        if currentHp > self.effectiveStats['HP']:
            self.hp = 100
        else:
            self.hp = (currentHp / self.effectiveStats['HP']) * 100

    # Returns False if pokemon faints from damage, true otherwise
    def take_damage(self, damage):
        if damage == 0:
            return True
        if self.effectiveStats['HP']:
            if self.substituteHP > 0:
                currentHp = self.effectiveStats['HP'] * (self.substituteHP * .01)
                currentHp -= damage
                self.substituteHP = max([0, (currentHp / self.effectiveStats['HP']) * 100])
                return True
            currentHp = self.effectiveStats['HP'] * (self.hp * .01)
        else:
            if self.substituteHP > 0:
                currentHp = self.leveledStats['HP'] * (self.substituteHP * .01)
                currentHp -= damage
                self.substituteHP = max([0, (currentHp / self.leveledStats['HP']) * 100])
                return True
            currentHp = self.leveledStats['HP'] * (self.hp * .01)

        # Factor sturdy/focus sash if full hp
        if ('Sturdy' in self.ability or 'Focus Sash' in self.item) and self.hp == 100 and damage >= currentHp:
            if 'Focus Sash' in self.item:
                self.item.remove('Focus Sash')
            damage = currentHp - 1

        # Other abilities
        elif ('Multiscale' in self.ability or 'Shadow Shield' in self.ability) and self.hp == 100:
            damage *= .5
        elif 'Stamina' in self.ability:
            self.boost_stat('Def', 1)

        currentHp -= damage
        if self.effectiveStats['HP'] is not None:
            self.hp = max([0, (currentHp / self.effectiveStats['HP']) * 100])
        else:
            self.hp = max([0, (currentHp / self.leveledStats['HP']) * 100])
        if self.hp == 0:
            self.fainted = True
            self.switch_out()
            return False

        # Consume berry if available
        elif self.hp < 50 and 'Sitrus Berry' in self.item:
            if 'Sitrus Berry' in self.item:
                self.item.remove('Sitrus Berry')
            self.hp += 25

        # Pop air balloon if damage is taken
        if damage > 0 and 'Air Balloon' in self.item:
            if 'Air Balloon' in self.item:
                self.item.remove('Air Balloon')

        self.lastDamageTaken = damage
        return True

    def take_life_orb_recoil(self):
        self.hp = max(0, self.hp - 10)
        if self.hp == 0:
            self.fainted = True
            return False
        return True

    def set_status_condition(self, status):
        # Type Immunities
        if self.type in ['steel', 'poison'] and status in ['PSN', 'TOX']:
            return
        elif 'electric' in self.type and status == 'PAR':
            return
        elif 'fire' in self.type and status == 'BRN':
            return
        elif 'ice' in self.type and status == 'FRZ':
            return

        # Ability Immunities
        if 'Vital Spirit' in self.ability and status == 'SLP':
            return
        elif 'Limber' in self.ability and status == 'PAR':
            return

        # Substitute blocks status
        if self.substituteHP > 0 and status in ['PSN', 'FRZ', 'BRN']:
            return

        # Chesto Berry cures sleep, Lum Berry cures all status conditions
        if ('Chesto Berry' in self.item and status == 'SLP') or 'Lum Berry' in self.item:
            self.item = []
            return

        if self.statusCondition is None:
            self.statusCondition = status

    def add_volatile_condition(self, condition):
        if self.substituteHP != 0 or condition in self.volatileConditions:
            return

        if self.lastUsedMove is None and condition == 'Encore':
            return

        # Type immunities
        if 'grass' in self.type and condition == 'Leech Seed':
            return

        # Ability Immunities
        if 'Oblivious' in self.ability and condition == 'Taunt':
            return
        elif 'Own Tempo' in self.ability and condition == 'Confused':
            return

        self.volatileConditions.append(condition)

    def remove_volatile_condition(self, condition):
        if condition in self.volatileConditions:
            self.volatileConditions.remove(condition)

    def switch_out(self):
        self.substituteHP = 0
        self.inBattle = False
        self.volatileConditions = []
        for stat in self.boosts:
            self.boosts[stat] = 0
        self.isDynamaxed = False
        self.lastUsedMove = None

        if self.fainted:
            return

        # Ability interactions
        if 'Regenerator' in self.ability:
            self.heal(self.leveledStats['HP'] * .33)
        elif 'Natural Cure' in self.ability:
            self.statusCondition = None

    def switch_in(self, entryHazards):
        stealthRockDamage = {
            'normal': 1, 'fighting': .5, 'flying': 2, 'poison': 1, 'ground': .5, 'rock': .5, 'bug': 2, 'ghost': 1,
            'steel': .5, 'fire': 2, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': 1, 'ice': 2, 'dragon': 1,
            'dark': 1, 'fairy': 1
        }
        switchedInSafely = True
        self.inBattle = True
        self.isRevealed = True
        if 'Heavy Duty Boots' in self.item or 'Magic Guard' in self.ability:
            return True
        if 'Spikes' in entryHazards:
            if ('flying' not in self.type) and ('Levitate' not in self.ability):
                switchedInSafely = self.take_damage(self.leveledStats['HP'] * 1/8)
        if 'Stealth Rock' in entryHazards:
            multiplier = 1
            for typing in self.type:
                multiplier *= stealthRockDamage[typing]
            switchedInSafely = self.take_damage(self.leveledStats['HP'] * 1/8 * multiplier)
        if 'Sticky Web' in entryHazards:
            if ('flying' not in self.type) and ('Levitate' not in self.ability):
                self.boosts['Spe'] -= -1
        if 'Toxic Spikes' in entryHazards:
            if ('flying' not in self.type) and ('steel' not in self.type) and ('poison' not in self.type) \
                    and ('Levitate' not in self.ability) and (self.statusCondition is None):
                self.statusCondition = 'PSN'
        return switchedInSafely

    def boost_stat(self, stat, statChange):
        # Clear body ignores negative stat changes
        if 'Clear Body' in self.ability and statChange < 0:
            return

        # Contrary inverts stat changes
        if 'Contrary' in self.ability:
            statChange *= -1

        # Simple doubles stat changes
        if 'Simple' in self.ability:
            statChange *= 2

        self.boosts[stat] += statChange
        if self.boosts[stat] > 6:
            self.boosts[stat] = 6
        elif self.boosts[stat] < -6:
            self.boosts[stat] = -6

        # Ability interactions with stat changes
        if 'Competitive' in self.ability and statChange < 0:
            self.boost_stat('Spa', 2)
        elif 'Defiant' in self.ability and statChange < 0:
            self.boost_stat('Atk', 2)

    def set_last_used_move(self, move):
        self.lastUsedMove = move


class BattleState:
    def __init__(self):
        self.opponentName = ''
        self.elo = None
        self.myTeam = []
        self.opponentTeam = []
        self.myLeadIndex = None
        self.opponentLeadIndex = None
        self.myDynamaxAvailable = True
        self.opponentDynamaxAvailable = True
        self.myField = {
            'reflect': {'isUp': False, 'minTurns': 0, 'maxTurns': 0},
            'lightScreen': {'isUp': False, 'minTurns': 0, 'maxTurns': 0},
            'auroraVeil': {'isUp': False, 'minTurns': 0, 'maxTurns': 0},
            'tailwind': {'isUp': False, 'turns': 0},
            'entryHazards': []
        }
        self.opponentField = {
            'reflect': {'isUp': False, 'minTurns': 0, 'maxTurns': 0},
            'lightScreen': {'isUp': False, 'minTurns': 0, 'maxTurns': 0},
            'auroraVeil': {'isUp': False, 'minTurns': 0, 'maxTurns': 0},
            'tailwind': {'isUp': False, 'turns': 0},
            'entryHazards': []  # Stealth Rocks, Spikes, Toxic Spikes, Sticky Web
        }
        self.weather = {
            'type': None,   # Rain, Sun, Hail, Sand
            'minTurns': 0,
            'maxTurns': 0
        }
        self.trickRoom = {
            'isUp': False,
            'turns': 0
        }
        self.terrain = {
            'type': None,    # Electric, Grassy, Misty, Psychic
            'minTurns': 0,
            'maxTurns': 0
        }
        self.iCanSwitch = True
        self.opponentCanSwitch = True
        self.turnsUntilMyWish = 0
        self.turnsUntilOpponentWish = 0
        self.turnNumber = 0

    def __deepcopy__(self, memodict={}):
        cls = self.__class__
        result = cls.__new__(cls)
        memodict[id(self)] = result
        for k, v in self.__dict__.items():
            setattr(result, k, deepcopy(v, memodict))
        return result

    def my_switch(self, index):
        if index == self.myLeadIndex:
            raise Exception("Switch index can't be the same as my team's lead index. Lead index = "
                            + str(self.myLeadIndex))
        self.myTeam[self.myLeadIndex].switch_out()
        result = self.myTeam[index].switch_in(self.myField['entryHazards'])
        self.myLeadIndex = index

        # Check if new lead has abilities that will activate upon switching in
        if 'Intimidate' in self.myTeam[self.myLeadIndex].ability:
            self.opponentTeam[self.opponentLeadIndex].boost_stat('Atk', -1)
        elif 'Drizzle' in self.myTeam[self.myLeadIndex].ability:
            self.set_weather('Rain')
        elif 'Drought' in self.myTeam[self.myLeadIndex].ability:
            self.set_weather('Sun')
        elif 'Sand Stream' in self.myTeam[self.myLeadIndex].ability:
            self.set_weather('Sandstorm')
        elif 'Snow Warning' in self.myTeam[self.myLeadIndex].ability:
            self.set_weather('Hail')
        elif 'Psychic Surge' in self.myTeam[self.myLeadIndex].ability:
            self.set_terrain('Psychic Terrain')
        elif 'Grassy Surge' in self.myTeam[self.myLeadIndex].ability:
            self.set_terrain('Grassy Terrain')
        elif 'Misty Surge' in self.myTeam[self.myLeadIndex].ability:
            self.set_terrain('Misty Terrain')
        elif 'Electric Surge' in self.myTeam[self.myLeadIndex].ability:
            self.set_terrain('Electric Terrain')
        elif 'Intrepid Sword' in self.myTeam[self.myLeadIndex].ability:
            self.myTeam[self.myLeadIndex].boost_stat('Atk', 1)
        elif 'Dauntless Shield' in self.myTeam[self.myLeadIndex].ability:
            self.myTeam[self.myLeadIndex].boost_stat('Def', 1)

        if not result:
            self.myTeam[index].inBattle = False
            return False
        return True

    def opponent_switch(self, index):
        if index == self.opponentLeadIndex:
            raise Exception("Switch index can't be the same as my opponent's lead index. Lead index = "
                            + str(self.opponentLeadIndex))
        self.opponentTeam[self.opponentLeadIndex].switch_out()
        result = self.opponentTeam[index].switch_in(self.opponentField['entryHazards'])
        self.opponentLeadIndex = index

        # Check if new lead has abilities that will activate upon switching in
        if 'Intimidate' in self.opponentTeam[self.opponentLeadIndex].ability:
            self.opponentTeam[self.opponentLeadIndex].boost_stat('Atk', -1)
        elif 'Drizzle' in self.opponentTeam[self.opponentLeadIndex].ability:
            self.set_weather('Rain')
        elif 'Drought' in self.opponentTeam[self.opponentLeadIndex].ability:
            self.set_weather('Sun')
        elif 'Sand Stream' in self.opponentTeam[self.opponentLeadIndex].ability:
            self.set_weather('Sandstorm')
        elif 'Snow Warning' in self.opponentTeam[self.opponentLeadIndex].ability:
            self.set_weather('Hail')
        elif 'Psychic Surge' in self.opponentTeam[self.opponentLeadIndex].ability:
            self.set_terrain('Psychic Terrain')
        elif 'Grassy Surge' in self.opponentTeam[self.opponentLeadIndex].ability:
            self.set_terrain('Grassy Terrain')
        elif 'Misty Surge' in self.opponentTeam[self.opponentLeadIndex].ability:
            self.set_terrain('Misty Terrain')
        elif 'Electric Surge' in self.opponentTeam[self.opponentLeadIndex].ability:
            self.set_terrain('Electric Terrain')
        elif 'Intrepid Sword' in self.opponentTeam[self.opponentLeadIndex].ability:
            self.opponentTeam[self.opponentLeadIndex].boost_stat('Atk', 1)
        elif 'Dauntless Shield' in self.opponentTeam[self.opponentLeadIndex].ability:
            self.opponentTeam[self.opponentLeadIndex].boost_stat('Def', 1)

        if not result:
            self.opponentTeam[index].inBattle = False
            return False
        return True

    def expend_my_dynamax(self):
        self.myDynamaxAvailable = False
        self.myTeam[self.myLeadIndex].isDynamaxed = True
        calculate_effective_stats(self.myTeam[self.myLeadIndex], self.myField, self)

    def expend_opponent_dynamax(self):
        self.opponentDynamaxAvailable = False
        self.opponentTeam[self.opponentLeadIndex].isDynamaxed = True
        calculate_effective_stats(self.opponentTeam[self.opponentLeadIndex], self.opponentField, self)

    def set_my_screen(self, screen, hasLightClay):
        self.myField[screen]['isUp'] = True
        if hasLightClay:
            self.myField[screen]['minTurns'] = 8
            self.myField[screen]['maxTurns'] = 8
        else:
            self.myField[screen]['minTurns'] = 5
            self.myField[screen]['maxTurns'] = 5

    def set_my_tailwind(self):
        self.myField['tailwind']['isUp'] = True
        self.myField['tailwind']['turns'] = 4

    def set_opponent_screen(self, screen, hasLightClay):
        self.opponentField[screen]['isUp'] = True
        if hasLightClay:
            self.opponentField[screen]['minTurns'] = 8
            self.opponentField[screen]['maxTurns'] = 8
        else:
            self.opponentField[screen]['minTurns'] = 5
            self.opponentField[screen]['maxTurns'] = 5

    def set_opponent_tailwind(self):
        self.opponentField['tailwind']['isUp'] = True
        self.opponentField['tailwind']['turns'] = 4

    def end_turn_procedure(self):
        # Take weather damage
        myLead = self.myTeam[self.myLeadIndex]
        opponentLead = self.opponentTeam[self.opponentLeadIndex]
        calculate_effective_stats(myLead, self.myField, self)
        calculate_effective_stats(opponentLead, self.opponentField, self)
        leads = [myLead, opponentLead]
        if self.weather['type'] == 'Sandstorm':
            for lead in leads:
                if not lead.fainted:
                    immune = False
                    for ability in lead.ability:
                        if ability in ['Sand Force', 'Sand Rush', 'Sand Veil']:
                            immune = True
                    for type in lead.type:
                        if type not in ['rock', 'steel', 'ground']:
                            immune = True
                    if not immune:
                        lead.take_damage(lead.leveledStats['HP'] * 1/16)
        elif self.weather['type'] == 'Hail':
            leads = [self.myTeam[self.myLeadIndex], self.opponentTeam[self.opponentLeadIndex]]
            for lead in leads:
                if not lead.fainted:
                    immune = False
                    for ability in lead.ability:
                        if ability in ['Ice Body', 'Snow Cloak', 'Magic Guard', 'Overcoat']:
                            immune = True
                    if 'ice' in lead.type:
                        immune = True
                    if not immune:
                        lead.take_damage(lead.leveledStats['HP'] * 1/16)
        # Take leftover healing
        for lead in leads:
            if 'Leftovers' in lead.item and not lead.fainted:
                lead.heal(lead.leveledStats['HP'] * 1/16)
        # Take status damage + and leech seed
        for lead in leads:
            if lead.statusCondition == 'BRN':
                lead.take_damage(lead.leveledStats['HP'] * 1/16)
            elif lead.statusCondition == 'PSN':
                lead.take_damage(lead.leveledStats['HP'] * 1/8)
            elif lead.statusCondition == 'TOX':
                if lead.nextToxicDamage is None:
                    lead.nextToxicDamage = 6.25
                lead.take_damage(lead.leveledStats['HP'] * lead.nextToxicDamage * .01)
        lead = self.myTeam[self.myLeadIndex]
        if 'Leech Seed' in lead.volatileConditions:
            damage = lead.leveledStats['HP'] * 1/8
            lead.take_damage(damage)
            self.opponentTeam[self.opponentLeadIndex].heal(damage)
        lead = self.opponentTeam[self.opponentLeadIndex]
        if 'Leech Seed' in lead.volatileConditions:
            damage = lead.leveledStats['HP'] * 1/8
            lead.take_damage(damage)
            self.myTeam[self.myLeadIndex].heal(damage)

        # Decrement screen turns
        screens = ['reflect', 'lightScreen', 'auroraVeil']
        for screen in screens:
            if self.myField[screen]['minTurns'] == 1:
                self.myField[screen]['isUp'] = False
                self.myField[screen]['minTurns'] = 0
                self.myField[screen]['maxTurns'] = 0
            elif self.myField[screen]['minTurns'] != 0:
                self.myField[screen]['minTurns'] -= 1
                self.myField[screen]['maxTurns'] -= 1
            if self.opponentField[screen]['minTurns'] == 1:
                self.opponentField[screen]['isUp'] = False
                self.opponentField[screen]['minTurns'] = 0
                self.opponentField[screen]['maxTurns'] = 0
            elif self.opponentField[screen]['minTurns'] != 0:
                self.opponentField[screen]['minTurns'] -= 1
                self.opponentField[screen]['maxTurns'] -= 1
        if self.myField['tailwind']['isUp']:
            if self.myField['tailwind']['turns'] == 1:
                self.myField['tailwind']['isUp'] = False
            else:
                self.myField['tailwind']['turns'] -= 1
        if self.opponentField['tailwind']['isUp']:
            if self.opponentField['tailwind']['turns'] == 1:
                self.opponentField['tailwind']['isUp'] = False
            else:
                self.opponentField['tailwind']['turns'] -= 1
        # Decrement terrain turns
        if self.terrain['type'] is not None:
            if self.terrain['minTurns'] == 1:
                self.terrain['type'] = None
                self.terrain['minTurns'] = 0
                self.terrain['maxTurns'] = 0
            else:
                self.terrain['minTurns'] -= 1
                self.terrain['maxTurns'] -= 1
        # Decrement Weather Turns
        if self.weather['type'] is not None:
            if self.weather['minTurns'] == 1:
                self.weather['type'] = None
                self.weather['minTurns'] = 0
                self.weather['maxTurns'] = 0
            else:
                self.weather['minTurns'] -= 1
                self.weather['maxTurns'] -= 1
        # Decrement trick room turns
        if self.trickRoom['isUp']:
            if self.trickRoom['turns'] == 1:
                self.trickRoom['isUp'] = False
                self.trickRoom['turns'] = 0
            else:
                self.trickRoom['turns'] -= 1
        # Decrement Dynamax Turns
        if self.myTeam[self.myLeadIndex].isDynamaxed:
            if self.myTeam[self.myLeadIndex].turnsDynamaxed == 2:
                self.myTeam[self.myLeadIndex].isDynamaxed = False
            else:
                self.myTeam[self.myLeadIndex].turnsDynamaxed += 1
        if self.opponentTeam[self.opponentLeadIndex].isDynamaxed:
            if self.opponentTeam[self.opponentLeadIndex].turnsDynamaxed == 2:
                self.opponentTeam[self.opponentLeadIndex].isDynamaxed = False
            else:
                self.opponentTeam[self.opponentLeadIndex].turnsDynamaxed += 1
        # Increase Toxic Damage
        if self.myTeam[self.myLeadIndex].statusCondition == 'TOX':
            self.myTeam[self.myLeadIndex].nextToxicDamage += 6.25
        if self.opponentTeam[self.opponentLeadIndex].statusCondition == 'TOX':
            self.opponentTeam[self.opponentLeadIndex].nextToxicDamage += 6.25
        # Convert drowsy
        if 'drowsy' in self.myTeam[self.myLeadIndex].volatileConditions:
            self.myTeam[self.myLeadIndex].volatileConditions.remove('Drowsy')
            if self.myTeam[self.myLeadIndex].statusCondition is None:
                self.myTeam[self.myLeadIndex].statusCondition = 'SLP'
        # Remove flinch
        self.myTeam[self.myLeadIndex].flinched = False
        self.opponentTeam[self.opponentLeadIndex].flinched = False
        # Remove protect
        self.myTeam[self.myLeadIndex].protected = False
        self.opponentTeam[self.opponentLeadIndex].protected = False
        # Decrement/Consume Wish
        if self.turnsUntilMyWish > 0:
            if self.turnsUntilMyWish == 1:
                self.myTeam[self.myLeadIndex].heal(self.myTeam[self.myLeadIndex].leveledStats['HP'] * .5)
            self.turnsUntilMyWish -= 1
        if self.turnsUntilOpponentWish > 0:
            if self.turnsUntilOpponentWish == 1:
                self.opponentTeam[self.opponentLeadIndex].heal(
                    self.opponentTeam[self.opponentLeadIndex].leveledStats['HP'] * .5)
            self.turnsUntilOpponentWish -= 1
        # Reset lastDamageTaken
        self.myTeam[self.myLeadIndex].lastDamageTaken = 0
        self.opponentTeam[self.opponentLeadIndex].lastDamageTaken = 0

    def remove_my_screens(self):
        screens = ['reflect', 'lightScreen', 'auroraVeil']
        for screen in screens:
            self.myField[screen]['isUp'] = False
            self.myField[screen]['minTurns'] = 0
            self.myField[screen]['maxTurns'] = 0

    def remove_opponents_screens(self):
        screens = ['reflect', 'lightScreen', 'auroraVeil']
        for screen in screens:
            self.opponentField[screen]['isUp'] = False
            self.opponentField[screen]['minTurns'] = 0
            self.opponentField[screen]['maxTurns'] = 0

    def set_weather(self, weather):
        if weather != self.weather['type']:
            self.weather['type'] = weather
            self.weather['minTurns'] = 5
            self.weather['maxTurns'] = 5

    def set_terrain(self, terrain):
        self.terrain['type'] = terrain
        self.terrain['minTurns'] = 5
        self.terrain['maxTurns'] = 5

    def set_trick_room(self):
        self.trickRoom['isUp'] = not self.trickRoom['isUp']
        if self.trickRoom['isUp']:
            self.trickRoom['turns'] = 5
        else:
            self.trickRoom['turns'] = 0

    def get_my_pokemon_remaining(self):
        members_remaining = 0
        for member in self.myTeam:
            if not member.fainted:
                members_remaining += 1
        return members_remaining

    def get_opponent_pokemon_remaining(self):
        members_remaining = 0
        for member in self.opponentTeam:
            if not member.fainted:
                members_remaining += 1
        for i in range(6 - len(self.opponentTeam)):
            members_remaining += 1
        return members_remaining

    def get_my_pokemon_revealed(self):
        members_revealed = 0
        for member in self.myTeam:
            if member.isRevealed:
                members_revealed += 1
        return members_revealed

    def get_opponent_pokemon_revealed(self):
        return len(self.opponentTeam)

    def get_my_team_statuses(self):
        statuses = 0
        for member in self.myTeam:
            if member.statusCondition is not None:
                statuses += 1
        return statuses

    def get_opponent_team_statuses(self):
        statuses = 0
        for member in self.opponentTeam:
            if member.statusCondition is not None:
                statuses += 1
        return statuses


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

accuracyStatChanges = {
    '3': 6,
    '2.67': 5,
    '2.33': 4,
    '2': 3,
    '1.67': 2,
    '1.33': 1,
    '0.75': -1,
    '0.6': -2,
    '0.5': -3,
    '0.43': -4,
    '0.38': -5,
    '0.33': -6
}


# Returns json file with possible random sets.
def updatePossibleSets():
    logging.info('Getting possible random battle sets json file.')
    try:
        url = requests.get('https://pkmn.github.io/randbats/data/gen8randombattle.json')
        sets = url.text
    except:
        logging.warning('Error grabbing online set data. Using old data.')
        with open('teams/old_sets.json', 'r') as setsFile:
            sets = setsFile.read()
            return sets
    localFile = open('teams/old_sets.json', 'w')
    localFile.write(sets)
    localFile.close()
    return sets


# Used to print off tooltip element for debugging purposes.
def printToolTips(driver):
    # Prints My Tool Tips
    logging.info("Switch button tool tips:")
    switchMenu = driver.find_element(By.CLASS_NAME, 'switchmenu')
    hover = ActionChains(driver)
    switchButtons = switchMenu.find_elements(By.TAG_NAME, 'button')
    for button in switchButtons:
        hover.move_to_element(button).perform()
        toolTip = driver.find_element(By.ID, 'tooltipwrapper')
        text = driver.execute_script("return arguments[0].innerHTML;", toolTip)
        logging.info(text)

    # Print my icon tool tips
    logging.info("My icon tooltips:")
    sideBar = driver.find_element(By.CLASS_NAME, 'trainer-near')
    sideIcons = sideBar.find_elements(By.CLASS_NAME, 'teamicons')
    for row in sideIcons:
        icons = row.find_elements(By.CLASS_NAME, 'has-tooltip')
        if icons is not None:
            for icon in icons:
                hover.move_to_element(icon).perform()
                toolTip = driver.find_element(By.ID, 'tooltipwrapper')
                text = driver.execute_script("return arguments[0].innerHTML;", toolTip)
                logging.info(text)

    # Prints opponents tool tips
    logging.info("Opponent tool tips:")
    sideBar = driver.find_element(By.CLASS_NAME, 'trainer-far')
    sideIcons = sideBar.find_elements(By.CLASS_NAME, 'teamicons')
    for row in sideIcons:
        icons = row.find_elements(By.CLASS_NAME, 'has-tooltip')
        if icons is not None:
            for icon in icons:
                hover.move_to_element(icon).perform()
                toolTip = driver.find_element(By.ID, 'tooltipwrapper')
                text = driver.execute_script("return arguments[0].innerHTML;", toolTip)
                logging.info(text)

    # Prints field condition tool tips
    elementGrab = driver.find_element(By.CLASS_NAME, 'turn')
    hover.move_to_element(elementGrab).perform()
    logging.info("Field condition tool tips:")
    toolTip = driver.find_element(By.ID, 'tooltipwrapper')
    text = driver.execute_script("return arguments[0].innerHTML;", toolTip)
    logging.info(text)


# Returns battleState object for AI calculations from showdown website.
async def getBattleState(driver, previousBattleState, elo):
    if previousBattleState:
        battleState = previousBattleState
        # Increment sleep turns if necessary
        if battleState.myTeam[battleState.myLeadIndex].statusCondition == 'SLP':
            battleState.myTeam[battleState.myLeadIndex].sleepTurns += 1
        if battleState.opponentTeam[battleState.opponentLeadIndex].statusCondition == 'SLP':
            battleState.opponentTeam[battleState.opponentLeadIndex].sleepTurns += 1
        if 'Confused' in battleState.myTeam[battleState.myLeadIndex].volatileConditions:
            battleState.myTeam[battleState.myLeadIndex].confusionTurns += 1
        if 'Confused' in battleState.opponentTeam[battleState.opponentLeadIndex].volatileConditions:
            battleState.opponentTeam[battleState.opponentLeadIndex].confusionTurns += 1

    else:
        battleState = BattleState()

    # Get opponent name + Elo
    if not previousBattleState:
        elementGrab = driver.find_element(By.CLASS_NAME, 'trainer-far')
        battleState.opponentName = elementGrab.text
        battleState.elo = elo

    # Grab my team
    logging.info("Obtaining my team's information")
    awaitElement(driver, By.CLASS_NAME, 'switchmenu')
    switchMenu = driver.find_element(By.CLASS_NAME, 'switchmenu')
    hover = ActionChains(driver)
    switchButtons = switchMenu.find_elements(By.TAG_NAME, 'button')
    if previousBattleState is not None:
        battleState.myTeam = previousBattleState.myTeam
        battleState.opponentTeam = previousBattleState.opponentTeam
    for button in switchButtons:
        hover.move_to_element(button).perform()
        toolTip = getToolTip(driver)
        # Get level
        nicknamed = False
        lvl100 = True
        tempLevel = None
        tempName = None
        elementGrab = toolTip.find_element(By.TAG_NAME, 'h2').find_elements(By.TAG_NAME, 'small')
        for element in elementGrab:
            if re.search('[L][0-9][0-9]', element.text):
                lvl100 = False
                tempLevel = int(element.text[1:])
            elif re.search('[(].*[)]', element.text):
                nicknamed = True
            else:
                logging.warning('Another unknown small tag found by name + level???\n' + element.text)
        if lvl100:
            tempLevel = 100

        # Get name
        if nicknamed:
            elementGrab = toolTip.find_element(By.TAG_NAME, 'h2').find_elements(By.TAG_NAME, 'small')
            if re.search('[L][0-9][0-9]', elementGrab[0].text):
                tempName = elementGrab[1].text[1:-1]
            else:
                tempName = elementGrab[0].text[1:-1]
        else:
            try:
                elementGrab = toolTip.find_element(By.TAG_NAME, 'h2').find_element(By.TAG_NAME, 'small').text
                tempName = toolTip.find_element(By.TAG_NAME, 'h2').text.replace(elementGrab, '').strip()
            except NoSuchElementException:
                tempName = toolTip.find_element(By.TAG_NAME, 'h2').text

        # Find pokemon's index in my team array
        teamIndex = len(battleState.myTeam)
        try:
            teamIndex = get_pokemon_index(battleState.myTeam, tempName)
        except NoSuchElementException:
            battleState.myTeam.append(Pokemon())
            battleState.myTeam[teamIndex].name = tempName
            battleState.myTeam[teamIndex].level = tempLevel
            teamIndex = get_pokemon_index(battleState.myTeam, tempName)

        # Get HP & if fainted
        elementGrab = toolTip.find_elements(By.TAG_NAME, 'p')
        if elementGrab[0].text.strip() == 'HP: (fainted)':
            battleState.myTeam[teamIndex].hp = 0
            battleState.myTeam[teamIndex].fainted = True
        else:
            battleState.myTeam[teamIndex].hp = float(elementGrab[0].text[4:elementGrab[0].text.index('%')])
            battleState.myTeam[teamIndex].fainted = False

        # Get Item
        # Check if there is an item equipped:
        if re.search('Item:', elementGrab[1].text):
            battleState.myTeam[teamIndex].item = [elementGrab[1].text[(elementGrab[1].text.index('Item:') + 6):]]
        else:
            battleState.myTeam[teamIndex].item = []

        # Get Ability
        if battleState.myTeam[teamIndex].item:
            battleState.myTeam[teamIndex].ability = [elementGrab[1].text[
                (elementGrab[1].text.index('Ability:') + 9):(elementGrab[1].text.index(' / '))]]
        else:
            battleState.myTeam[teamIndex].ability = [elementGrab[1].text[(elementGrab[1].text.index('Ability:') + 9):]]

        # Get Status Condition
        elementGrab = toolTip.find_elements(By.TAG_NAME, 'p')
        for element in elementGrab:
            try:
                statusElement = element.find_element(By.TAG_NAME, 'span')
                battleState.myTeam[teamIndex].statusCondition = statusElement.text
                break
            except NoSuchElementException:
                battleState.myTeam[teamIndex].statusCondition = None
                battleState.myTeam[teamIndex].sleepTurns = 0

        # Get moves from switch tooltips
        if not battleState.myTeam[teamIndex].lookupPerformed:
            elementGrab = toolTip.find_element(By.CLASS_NAME, 'section').text
            for move in elementGrab.split('\n'):
                if (move not in battleState.myTeam[teamIndex].knownMoveNames) and move[:3] != "Max":
                    battleState.myTeam[teamIndex].knownMoveNames.append(move[2:])

    # Reset in battle for all pokemon on my team
    for member in battleState.myTeam:
        member.inBattle = False

    try:
        # Get inBattle
        elementGrab = driver.find_element(By.CLASS_NAME, 'tooltips')
        elementGrab = elementGrab.find_elements(By.CSS_SELECTOR, '*')
        hover.move_to_element(elementGrab[3]).perform()
        toolTip = getToolTip(driver)
        nicknamed = False
        elementGrab = toolTip.find_element(By.TAG_NAME, 'h2').find_elements(By.TAG_NAME, 'small')
        for element in elementGrab:
            if re.search('[(].*[)]', element.text):
                nicknamed = True
        if nicknamed:
            elementGrab = toolTip.find_element(By.TAG_NAME, 'h2').find_elements(By.TAG_NAME, 'small')
            if re.search('[L][0-9][0-9]', elementGrab[0].text):
                hoverName = elementGrab[1].text[1:-1]
            else:
                hoverName = elementGrab[0].text[1:-1]
        else:
            try:
                elementGrab = toolTip.find_element(By.TAG_NAME, 'h2').find_element(By.TAG_NAME, 'small').text
                hoverName = toolTip.find_element(By.TAG_NAME, 'h2').text.replace(elementGrab, '').strip()
            except NoSuchElementException:
                hoverName = toolTip.find_element(By.TAG_NAME, 'h2').text
        battleState.myLeadIndex = get_pokemon_index(battleState.myTeam, hoverName)
        battleState.myTeam[battleState.myLeadIndex].inBattle = True
        # Check if I have shadow tag active
        if re.search('Wobbuffet|Gothitelle|Dugtrio', battleState.myTeam[battleState.myLeadIndex].name):
            battleState.opponentCanSwitch = False

        # Get Volatile Conditions & Stat Changes
        battleState.myTeam[battleState.myLeadIndex].volatileConditions = []
        for stat in battleState.myTeam[battleState.myLeadIndex].boosts.keys():
            battleState.myTeam[battleState.myLeadIndex].boosts[stat] = 0
        try:
            elementGrab = driver.find_element(By.CLASS_NAME, 'rstatbar').find_element(By.CLASS_NAME, 'status')
            elementGrab = elementGrab.find_elements(By.CSS_SELECTOR, '*')
            battleState.myTeam[battleState.myLeadIndex] = \
                getVolatileConditions(battleState.myTeam[battleState.myLeadIndex], elementGrab)
            if battleState.myTeam[battleState.myLeadIndex].isDynamaxed:
                battleState.myTeam[battleState.myLeadIndex].turnsDynamaxed = \
                    previousBattleState.myTeam[previousBattleState.myLeadIndex].turnsDynamaxed + 1
                battleState.myDynamaxAvailable = False
        except NoSuchElementException:
            pass
        if 'Confused' not in battleState.myTeam[battleState.myLeadIndex].volatileConditions:
            battleState.myTeam[battleState.myLeadIndex].confusionTurns = 0
    except NoSuchElementException:
        battleState.myTeam[battleState.myLeadIndex].inBattle = False

    # Reset last used move for all Pokemon on the bench
    for member in battleState.myTeam:
        if not member.inBattle:
            member.lastUsedMove = None

    # Get side icon information
    logging.info('Grabbing my side icon information')
    mySideBar = driver.find_element(By.CLASS_NAME, 'trainer-near')
    mySideIcons = mySideBar.find_elements(By.CLASS_NAME, 'teamicons')
    for row in mySideIcons:
        icons = row.find_elements(By.CLASS_NAME, 'has-tooltip')
        if icons is not None:
            for icon in icons:
                hover.move_to_element(icon).perform()
                toolTip = getToolTip(driver)
                # Find isRevealed
                nicknamed = False
                elementGrab = toolTip.find_element(By.TAG_NAME, 'h2').find_elements(By.TAG_NAME, 'small')
                for element in elementGrab:
                    if re.search('[(].*[)]', element.text):
                        nicknamed = True
                if nicknamed:
                    elementGrab = toolTip.find_element(By.TAG_NAME, 'h2').find_elements(By.TAG_NAME, 'small')
                    if re.search('[L][0-9][0-9]', elementGrab[0].text):
                        hoverName = elementGrab[1].text[1:-1]
                    else:
                        hoverName = elementGrab[0].text[1:-1]
                else:
                    try:
                        elementGrab = toolTip.find_element(By.TAG_NAME, 'h2').find_element(By.TAG_NAME, 'small').text
                        hoverName = toolTip.find_element(By.TAG_NAME, 'h2').text.replace(elementGrab, '').strip()
                    except NoSuchElementException:
                        hoverName = toolTip.find_element(By.TAG_NAME, 'h2').text
                teamIndex = get_pokemon_index(battleState.myTeam, hoverName)
                battleState.myTeam[teamIndex].isRevealed = True
                if battleState.myTeam[teamIndex].statusCondition == 'TOX':
                    toxicDamage = {
                        6: 6.25,
                        12: 12.5,
                        18: 18.75,
                        25: 25,
                        31: 31.25,
                        37: 37.5,
                        43: 43.75,
                        50: 50,
                        56: 56.25,
                        62: 62.5,
                        68: 68.75,
                        75: 75,
                        81: 81.25,
                        87: 87.5,
                        93: 93.75,
                        100: 100
                    }
                    elementGrab = toolTip.find_elements(By.TAG_NAME, 'p')
                    try:
                        battleState.myTeam[teamIndex].nextToxicDamage = \
                            toxicDamage[int(elementGrab[0].text[(elementGrab[0].text.index('damage:') + 8):-1])]
                    except KeyError:
                        battleState.myTeam[teamIndex].nextToxicDamage = \
                            int(elementGrab[0].text[(elementGrab[0].text.index('damage:') + 8):-1])
                else:
                    battleState.myTeam[teamIndex].nextToxicDamage = None

    # Grab opponent's team
    logging.info("Grabbing opponent's team information.")
    # Get # of opposing pokemon
    elementGrab = driver.find_element(By.CLASS_NAME, 'trainer-far')
    opposingTeamRows = elementGrab.find_elements(By.CLASS_NAME, 'teamicons')
    for row in opposingTeamRows:
        icons = row.find_elements(By.CLASS_NAME, 'has-tooltip')
        if icons is not None:
            for icon in icons:
                hover.move_to_element(icon).perform()
                toolTip = getToolTip(driver)

                # Find Level
                tempLevel = None
                nicknamed = False
                lvl100 = True
                elementGrab = toolTip.find_element(By.TAG_NAME, 'h2').find_elements(By.TAG_NAME, 'small')
                for element in elementGrab:
                    if re.search('[L][0-9][0-9]', element.text):
                        lvl100 = False
                        tempLevel = int(element.text[1:])
                    elif re.search('[(].*[)]', element.text):
                        nicknamed = True
                    else:
                        print('Another unknown small tag found by name + level???\n' + element.text)
                if lvl100:
                    tempLevel = 100

                # Find Name
                if nicknamed:
                    elementGrab = toolTip.find_element(By.TAG_NAME, 'h2').find_elements(By.TAG_NAME, 'small')
                    if re.search('[L][0-9][0-9]', elementGrab[0].text):
                        tempName = elementGrab[1].text[1:-1]
                    else:
                        tempName = elementGrab[0].text[1:-1]
                else:
                    try:
                        elementGrab = toolTip.find_element(By.TAG_NAME, 'h2').find_element(By.TAG_NAME, 'small').text
                        tempName = toolTip.find_element(By.TAG_NAME, 'h2').text.replace(elementGrab, '').strip()
                    except NoSuchElementException:
                        tempName = toolTip.find_element(By.TAG_NAME, 'h2').text

                # Find icon's index in battleState
                teamIndex = len(battleState.opponentTeam)
                try:
                    teamIndex = get_pokemon_index(battleState.opponentTeam, tempName)
                except NoSuchElementException:
                    battleState.opponentTeam.append(Pokemon())
                    battleState.opponentTeam[teamIndex].name = tempName
                    battleState.opponentTeam[teamIndex].level = tempLevel

                # Mark as revealed
                battleState.opponentTeam[teamIndex].isRevealed = True

                # Find HP
                elementGrab = toolTip.find_elements(By.TAG_NAME, 'p')
                if elementGrab[0].text.strip() == 'HP: (fainted)':
                    battleState.opponentTeam[teamIndex].hp = 0
                    battleState.opponentTeam[teamIndex].fainted = True
                else:
                    battleState.opponentTeam[teamIndex].hp = float(elementGrab[0].text[4:elementGrab[0].text.index('%')])
                    battleState.opponentTeam[teamIndex].fainted = False

                # Try to find item and known abilities
                elementGrab = toolTip.find_elements(By.TAG_NAME, 'p')
                for paragraph in elementGrab:
                    if re.search(r"Item: ", paragraph.text):
                        battleState.opponentTeam[teamIndex].item = [paragraph.text[paragraph.text.index('Item: ') + 6:]]
                    elif re.search(r"Ability: ", paragraph.text):
                        battleState.opponentTeam[teamIndex].ability = [paragraph.text[paragraph.text.index('Ability: ') + 9]]

                # Find known moves
                movesRevealed = True
                revealedMoveList = []
                try:
                    rawMoveText = toolTip.find_element(By.CLASS_NAME, 'section').text
                    revealedMoveList = rawMoveText.split('\n')
                    for i in range(len(revealedMoveList)):
                        if revealedMoveList[i][:3] != "Max":
                            try:
                                revealedMoveList[i] = revealedMoveList[i][2:(revealedMoveList[i].index('(') - 1)]
                            except ValueError:
                                pass
                except NoSuchElementException:
                    movesRevealed = False
                if movesRevealed:
                    battleState.opponentTeam[teamIndex].knownMoveNames = revealedMoveList
                else:
                    battleState.opponentTeam[teamIndex].knownMoveNames = []

                # Find status condition
                elementGrab = toolTip.find_elements(By.TAG_NAME, 'p')
                for element in elementGrab:
                    try:
                        statusElement = element.find_element(By.TAG_NAME, 'span')
                        battleState.opponentTeam[teamIndex].statusCondition = statusElement.text
                        break
                    except NoSuchElementException:
                        battleState.opponentTeam[teamIndex].statusCondition = None
                        battleState.opponentTeam[teamIndex].sleepTurns = 0
                if battleState.opponentTeam[teamIndex].statusCondition == 'TOX':
                    toxicDamage = {
                        6: 6.25,
                        12: 12.5,
                        18: 18.75,
                        25: 25,
                        31: 31.25,
                        37: 37.5,
                        43: 43.75,
                        50: 50,
                        56: 56.25,
                        62: 62.5,
                        68: 68.75,
                        75: 75,
                        81: 81.25,
                        87: 87.5,
                        93: 93.75,
                        100: 100
                    }
                    elementGrab = toolTip.find_elements(By.TAG_NAME, 'p')
                    try:
                        battleState.opponentTeam[teamIndex].nextToxicDamage = \
                            toxicDamage[int(elementGrab[0].text[(elementGrab[0].text.index('damage:') + 8):-1])]
                    except KeyError:
                        battleState.opponentTeam[teamIndex].nextToxicDamage = \
                            int(elementGrab[0].text[(elementGrab[0].text.index('damage:') + 8):-1])
                else:
                    battleState.opponentTeam[teamIndex].nextToxicDamage = None

    # Find volatile conditions + in battle
    # Reset in battle for opponent's team
    for member in battleState.opponentTeam:
        member.inBattle = False
    # Find opponent's current pokemon's index
    elementGrab = driver.find_element(By.CLASS_NAME, 'tooltips')
    elementGrab = elementGrab.find_elements(By.CSS_SELECTOR, '*')
    hover.move_to_element(elementGrab[2]).perform()
    try:
        toolTip = getToolTip(driver)
        nicknamed = False
        elementGrab = toolTip.find_element(By.TAG_NAME, 'h2').find_elements(By.TAG_NAME, 'small')
        for element in elementGrab:
            if re.search('[(].*[)]', element.text):
                nicknamed = True
        if nicknamed:
            elementGrab = toolTip.find_element(By.TAG_NAME, 'h2').find_elements(By.TAG_NAME, 'small')
            if re.search('[L][0-9][0-9]', elementGrab[0].text):
                hoverName = elementGrab[1].text[1:-1]
            else:
                hoverName = elementGrab[0].text[1:-1]
        else:
            try:
                elementGrab = toolTip.find_element(By.TAG_NAME, 'h2').find_element(By.TAG_NAME, 'small').text
                hoverName = toolTip.find_element(By.TAG_NAME, 'h2').text.replace(elementGrab, '').strip()
            except NoSuchElementException:
                hoverName = toolTip.find_element(By.TAG_NAME, 'h2').text
        if hoverName == '8':
            hoverName = 'Wishiwashi'

        # Get opponent's lead pokemon
        teamIndex = get_pokemon_index(battleState.opponentTeam, hoverName)
        battleState.opponentLeadIndex = teamIndex
        battleState.opponentTeam[teamIndex].volatileConditions = []
        for stat in battleState.opponentTeam[teamIndex].boosts.keys():
            battleState.opponentTeam[teamIndex].boosts[stat] = 0

        battleState.opponentTeam[teamIndex].inBattle = True

        # Check for shadow tag
        if re.search('Wobbuffet|Gothitelle|Dugtrio', battleState.opponentTeam[teamIndex].name):
            battleState.iCanSwitch = False

        # Get opponent's volatile conditions
        elementGrab = driver.find_element(By.CLASS_NAME, 'lstatbar').find_element(By.CLASS_NAME, 'status')
        try:
            elementGrab = elementGrab.find_elements(By.CSS_SELECTOR, '*')
            battleState.opponentTeam[teamIndex] = getVolatileConditions(battleState.opponentTeam[teamIndex], elementGrab)
            if battleState.opponentTeam[teamIndex].isDynamaxed:
                battleState.opponentTeam[teamIndex].turnsDynamaxed = previousBattleState.opponentTeam[teamIndex].turnsDynamaxed + 1
                battleState.opponentDynamaxAvailable = False
        except NoSuchElementException:
            pass
        if 'Confused' not in battleState.opponentTeam[battleState.opponentLeadIndex].volatileConditions:
            battleState.opponentTeam[battleState.opponentLeadIndex].confusionTurns = 0

        # Get opponent's last used move
        elementGrab = driver.find_elements(By.CLASS_NAME, 'battle-history')
        for k in reversed(range(len(elementGrab))):
            if (re.search('opposing', elementGrab[k].text)) and (re.search('used', elementGrab[k].text)):
                try:
                    battleState.opponentTeam[teamIndex].lastUsedMove = \
                        adjust_name(elementGrab[k].find_element(By.TAG_NAME, 'strong').text)
                    break
                except NoSuchElementException:
                    continue
    except NoSuchElementException:
        battleState.opponentTeam[battleState.opponentLeadIndex].inBattle = False

    # Get field conditions
    elementGrab = driver.find_element(By.CLASS_NAME, 'turn')
    battleState.turnNumber = elementGrab.text.split(' ')[-1]
    hover.move_to_element(elementGrab).perform()
    toolTip = getToolTip(driver)

    # Grab weather/terrain/Trick Room
    elementGrab = toolTip.find_elements(By.TAG_NAME, 'p')
    for element in elementGrab:
        conditionText = element.text.split('\n')
        for text in conditionText:
            if re.search('Rain|Sun|Hail|Sandstorm', text):
                battleState.weather['type'] = text.split(' ')[0]
                battleState.weather['minTurns'] = int(text[text.index('(') + 1])
                if re.search('or', text):
                    battleState.weather['maxTurns'] = int(text[text.index(')') - 7])
                else:
                    battleState.weather['maxTurns'] = battleState.weather['minTurns']
            elif re.search('Terrain', text):
                battleState.terrain['type'] = text[0:(text.index('(') - 1)]
                battleState.terrain['minTurns'] = int(text[text.index('(') + 1])
                if re.search('or', text):
                    battleState.terrain['maxTurns'] = int(text[text.index(')') - 7])
                else:
                    battleState.terrain['maxTurns'] = battleState.terrain['minTurns']
            elif re.search('Trick Room', text) is not None:
                battleState.trickRoom['isUp'] = True
                battleState.trickRoom['turns'] = int(text[text.index('(') + 1])

    # Grab screens, entry hazards, tailwind
    logging.info('Grabbing field conditions.')
    elementGrab = toolTip.find_elements(By.CLASS_NAME, 'section')
    for element in elementGrab:
        conditionText = element.text.split('\n')
        if re.search('Trace_AI', element.text):
            battleState.myField = getFieldConditions(battleState.myField, conditionText, battleState.opponentName)
        else:
            battleState.opponentField = getFieldConditions(battleState.opponentField, conditionText, battleState.opponentName)

    # Fill in information for each team from pokeapi, if not filled in already
    logging.info('Performing api lookups for my team')
    async with aiopoke.AiopokeClient() as session:
        myTasks = []
        for index, pokemon in enumerate(battleState.myTeam):
            if not pokemon.lookupPerformed:
                try:
                    previousForm = previousBattleState.myTeam[get_pokemon_index(previousBattleState.myTeam, pokemon.name)]
                except:
                    previousForm = None
                task = asyncio.ensure_future(async_pokeapi_request(session, pokemon, previousForm))
                myTasks.append(task)
        if myTasks:
            battleState.myTeam = await asyncio.gather(*myTasks)
    await session.close()

    logging.info("Performing api lookups for opponent's team")
    async with aiopoke.AiopokeClient() as session:
        opponentTasks = []
        for index, pokemon in enumerate(battleState.opponentTeam):
            if not pokemon.lookupPerformed and pokemon.isRevealed:
                try:
                    previousForm = previousBattleState.opponentTeam[get_pokemon_index(previousBattleState.opponentTeam, pokemon.name)]
                except:
                    previousForm = None
                task = asyncio.ensure_future(async_pokeapi_request(session, pokemon, previousForm))
                opponentTasks.append(task)
        if opponentTasks:
            await asyncio.gather(*opponentTasks)
    await session.close()

    return battleState


def getToolTip(driver):
    toolTip = driver.find_element(By.ID, 'tooltipwrapper')
    toolTip = toolTip.find_element(By.CLASS_NAME, 'tooltipinner')
    toolTip = toolTip.find_element(By.CSS_SELECTOR, '*')
    return toolTip


# Returns list of possible max moves, based on known moves if all 4 are known, possible moves otherwise.
async def get_max_moves(session, pokemon):
    maxMoves = []
    maxMoveNames = {
        'normal': 'max-strike',
        'fighting': 'max-knuckle',
        'flying': 'max-airstream',
        'poison': 'max-ooze',
        'ground': 'max-quake',
        'rock': 'max-rockfall',
        'bug': 'max-flutterby',
        'ghost': 'max-phantasm',
        'steel': 'max-steelspike',
        'fire': 'max-flare',
        'water': 'max-geyser',
        'grass': 'max-overgrowth',
        'electric': 'max-lightning',
        'psychic': 'max-mindstorm',
        'ice': 'max-hailstorm',
        'dragon': 'max-wyrmwind',
        'dark': 'max-darkness',
        'fairy': 'max-starfall'
    }
    maxMovePowerTable = {
        'lowerPower': [10, 45, 55, 65, 75, 110, 150],
        'upperPower': [40, 50, 60, 70, 100, 140, 250],
        'otherMaxMovePower': [90, 100, 110, 120, 130, 140, 150],
        'maxFightingAndPoisonPower': [70, 75, 80, 85, 90, 95, 100]
    }
    moveExceptions = {
        'gyro-ball': 130,
        'low-kick': 100,
        'grass-knot': 130,
        'seismic-toss': 75,
        'heavy-slam': 130
    }
    if len(pokemon.knownMoves) < 4:
        moveList = pokemon.possibleMoves
    else:
        moveList = pokemon.knownMoves
    tasks = []
    for move in moveList:
        if move.damage_class.name == 'status':
            tasks.append(asyncio.ensure_future(pokeapi_move_request(session, 'max-guard')))
            continue
        tasks.append(asyncio.ensure_future(pokeapi_move_request(session, maxMoveNames[move.type.name])))
    maxMoves = await asyncio.gather(*tasks)
    # Calculate max move power based on the table above.
    for k in range(len(moveList)):
        if moveList[k].damage_class.name == 'status':
            continue
        for i in range(7):
            if moveList[k].power in range(maxMovePowerTable['lowerPower'][i], maxMovePowerTable['upperPower'][i] + 1):
                if moveList[k].type.name == 'fighting' or moveList[k].type.name == 'poison':
                    maxMoves[k].power = maxMovePowerTable['maxFightingAndPoisonPower'][i]
                    break
                else:
                    maxMoves[k].power = maxMovePowerTable['otherMaxMovePower'][i]
                    break
        if maxMoves[k].power is None and maxMoves[k].name != 'max-guard':
            maxMoves[k].power = moveExceptions[moveList[k].name]
        maxMoves[k].damage_class.name = moveList[k].damage_class.name
    return maxMoves


# Get entry hazards and active screens from the turn counter.
def getFieldConditions(field, conditionText, opponentName):
    field = {
            'reflect': {'isUp': False, 'minTurns': 0, 'maxTurns': 0},
            'lightScreen': {'isUp': False, 'minTurns': 0, 'maxTurns': 0},
            'auroraVeil': {'isUp': False, 'minTurns': 0, 'maxTurns': 0},
            'tailwind': {'isUp': False, 'turns': 0},
            'entryHazards': []
        }
    for text in conditionText:
        if re.search('Trace_AI', text) or re.search(opponentName, text):
            continue
        elif re.search('(no conditions)', text):
            break
        elif re.search('Reflect', text):
            field['reflect']['isUp'] = True
            field['reflect']['minTurns'] = int(text[text.index('(') + 1])
            if re.search('or', text):
                field['reflect']['maxTurns'] = int(text[text.index(')') - 7])
            else:
                field['reflect']['maxTurns'] = field['reflect']['minTurns']
        elif re.search('Light Screen', text):
            field['lightScreen']['isUp'] = True
            field['lightScreen']['minTurns'] = int(text[text.index('(') + 1])
            if re.search('or', text):
                field['lightScreen']['maxTurns'] = int(text[text.index(')') - 7])
            else:
                field['lightScreen']['maxTurns'] = field['lightScreen']['minTurns']
        elif re.search('Aurora Veil', text):
            field['auroraVeil']['isUp'] = True
            field['auroraVeil']['minTurns'] = int(text[text.index('(') + 1])
            if re.search('or', text):
                try:
                    field['auroraVeil']['maxTurns'] = int(text[text.index(')') - 7])
                except ValueError:
                    field['auroraVeil']['maxTurns'] = field['auroraVeil']['minTurns']
            else:
                field['auroraVeil']['maxTurns'] = field['auroraVeil']['minTurns']
        elif re.search('Tailwind', text):
            field['tailwind']['isUp'] = True
            field['tailwind']['turns'] = int(text[text.index('(') + 1])
        else:
            field['entryHazards'].append(text)
    return field


# Grab volatile conditions from below the health bar.
def getVolatileConditions(pokemon, elementList):
    pokemon.isDynamaxed = False
    for element in elementList:
        # Make sure status condition is not added to the volatile condition list
        if element.text == pokemon.statusCondition:
            continue
        # Check if status is a stat change
        if re.search(r'[0-4](\.\d\d?)?×', element.text):
            # Get the stat boost stage from the element text
            try:
                statModifier = statChanges[re.search(r'[0-4](\.\d\d?)?', element.text).group()]
            except KeyError:
                statModifier = accuracyStatChanges[re.search(r'[0-4](\.\d\d?)?', element.text).group()]
            statText = element.text[-3:]
            if statText == 'Atk':
                pokemon.boosts['Atk'] = statModifier
            elif statText == 'Def':
                pokemon.boosts['Def'] = statModifier
            elif statText == 'SpA':
                pokemon.boosts['Spa'] = statModifier
            elif statText == 'SpD':
                pokemon.boosts['SpD'] = statModifier
            elif statText == 'Spe':
                pokemon.boosts['Spe'] = statModifier
            elif statText == 'ion':
                pokemon.boosts['Eva'] = statModifier
            elif statText == 'acy':
                pokemon.boosts['Acc'] = statModifier
            else:
                print(
                    'Stat modifier not accounted for:\nstatText: ' + statText + '\nstatModifier: ' + statModifier)
        elif element.text == 'Dynamaxed':
            pokemon.isDynamaxed = True
        elif element.text == 'Balloon':
            pokemon.item = ['Air Balloon']
        else:
            pokemon.volatileConditions.append(element.text)
    return pokemon


# Gets the index for a pokemon in a team object.
def get_pokemon_index(team, pokemonName):
    multiforms = {
        'Wishiwashi-School': 'Wishiwashi',
        'Aegislash-Blade': 'Aegislash',
        'Basculin-Blue-Striped': 'Basculin',
        'Mimikyu-Busted': 'Mimikyu',
        'Morpeko-Hangry': 'Morpeko',
        'Eiscue-Noice': 'Eiscue'
    }
    if 'Zygarde' in pokemonName:
        for index, pokemon in enumerate(team):
            if pokemon.name in ['Zygarde-10', 'Zygarde']:
                return index
    if pokemonName in multiforms:
        pokemonName = multiforms[pokemonName]
    for index, pokemon in enumerate(team):
        if pokemon.name == pokemonName:
            return index
    logging.warning('Pokemon not found in team. Hover name: ' + pokemonName)
    raise NoSuchElementException


# Fills in known moves from previous team in battle state object. Returns pokemon object
def fill_known_moves(pokemon, previousPokemon):
    # Fill possible moves using previous BattleState team array if it exists.
    logging.info('Grabbing possible moves for ' + pokemon.name)
    returnList = []
    if previousPokemon is not None:
        returnList = previousPokemon.knownMoves
    # Fill in known move information
    if len(pokemon.knownMoves) < len(pokemon.knownMoveNames):
        for name in pokemon.knownMoveNames:
            found = False
            for move in pokemon.knownMoves:
                if adjust_name(name) == move.name:
                    found = True
                    returnList.append(move)
                    break
            if not found:
                for move in pokemon.possibleMoves:
                    if adjust_name(name) == move.name:
                        returnList.append(move)
    return returnList


# Takes a pokemon object and team array from previous battle state and returns a pokemon object with base stats
# adjusted to it's level, type, and weight, as well as filling in possible move information
async def async_pokeapi_request(session, pokemon, previousPokemon):
    # All random battle pokemon have 85 EVs and 31 IVs in every stat with a neutral nature, unless stated otherwise in
    # the json file.

    # HP = floor(0.01 x (2 x Base + IV + floor(0.25 x EV)) x Level) + Level + 10
    # Other Stats = (floor(0.01 x (2 x Base + IV + floor(0.25 x EV)) x Level) + 5) x Nature

    returnPokemon = pokemon
    logging.info("Performing api lookup for " + pokemon.name)
    multiforms = {
        'Wishiwashi-School': 'Wishiwashi',
        'Aegislash-Blade': 'Aegislash',
        'Basculin-Blue-Striped': 'Basculin',
        'Mimikyu-Busted': 'Mimikyu',
        'Morpeko-Hangry': 'Morpeko',
        'Eiscue-Noice': 'Eiscue'
    }
    if pokemon.name in multiforms:
        pokemon.name = multiforms[pokemon.name]

    # Check for different ev's/ivs
    attackAdjusted = False
    speedAdjusted = False
    # Open the random set json file
    allSets = get_sets_json_data()
    # Adds -Gmax to name if necessary.
    jsonPokemonName = pokemon.name
    if pokemon.name not in allSets:
        if pokemon.name == 'Wishiwashi':
            jsonPokemonName = 'Wishiwashi-School'
        elif pokemon.name == 'Changed forme: Wishiwashi-School':
            jsonPokemonName = 'Wishiwashi-School'
            pokemon.name = 'Wishiwashi'
        elif 'Pikachu' in jsonPokemonName:
            jsonPokemonName = 'Pikachu'
        elif pokemon.name == 'Gastrodon-East':
            jsonPokemonName = 'Gastrodon'
        else:
            logging.info('Pokemon not found. Adding -Gmax to name')
            jsonPokemonName = pokemon.name + '-Gmax'
    if 'evs' in allSets[jsonPokemonName]:
        for stat in allSets[jsonPokemonName]['evs']:
            if 'atk' in allSets[jsonPokemonName]['evs']:
                attackAdjusted = True
                continue
            elif 'spe' in allSets[jsonPokemonName]['evs']:
                speedAdjusted = True
    adjustedName = adjust_name(pokemon.name)
    timeStart = time.time()
    pokemonRequest = await session.get_pokemon(adjustedName)
    timeEnd = time.time()
    timeTotal = timeStart - timeEnd
    logging.info('Lookup for ' + pokemon.name + ' in ' + str(timeTotal))

    # Calculate HP
    returnPokemon.leveledStats['HP'] = math.floor(.01 * (2 * pokemonRequest.stats[0].base_stat + 31 + math.floor(.25 * 85)) * pokemon.level) + pokemon.level + 10

    # Calculate Attack
    ev = 85
    iv = 31
    if attackAdjusted:
        ev = 0
        iv = 0
    returnPokemon.leveledStats['Atk'] = math.floor(.01 * (2 * pokemonRequest.stats[1].base_stat + iv + math.floor(.25 * ev)) * pokemon.level) + 5

    # Calculate Defense
    returnPokemon.leveledStats['Def'] = math.floor(.01 * (2 * pokemonRequest.stats[2].base_stat + 31 + math.floor(.25 * 85)) * pokemon.level) + 5

    # Calculate Special Attack
    returnPokemon.leveledStats['Spa'] = math.floor(.01 * (2 * pokemonRequest.stats[3].base_stat + 31 + math.floor(.25 * 85)) * pokemon.level) + 5

    # Calculate Special Defense
    returnPokemon.leveledStats['SpD'] = math.floor(.01 * (2 * pokemonRequest.stats[4].base_stat + 31 + math.floor(.25 * 85)) * pokemon.level) + 5

    # Calculate Speed
    ev = 85
    iv = 31
    if speedAdjusted:
        ev = 0
        iv = 0
    returnPokemon.leveledStats['Spe'] = math.floor(.01 * (2 * pokemonRequest.stats[5].base_stat + iv + math.floor(.25 * ev)) * pokemon.level) + 5

    # If Silvally, get type
    if re.search(r"Silvally", returnPokemon.name):
        try:
            returnPokemon.type.append(returnPokemon.name[returnPokemon.name.index('-') + 1:].lower())
        except ValueError:
            returnPokemon.type.append('normal')
    # Grab Type
    else:
        for typeIndex in pokemonRequest.types:
            returnPokemon.type.append(typeIndex.type.name)

    # Get abilities if not already found
    if returnPokemon.ability is None:
        returnPokemon.ability = allSets[jsonPokemonName]['abilities']

    # Get possible items if not known
    if not returnPokemon.item:
        try:
            returnPokemon.item = allSets[jsonPokemonName]['items']
        except KeyError:
            returnPokemon.item = []

    # Get weight
    returnPokemon.weight = pokemonRequest.weight

    # Get possible moves
    timeStart = time.time()
    possibleMoves = []
    for moveName in allSets[jsonPokemonName]['moves']:
        possibleMoves.append(adjust_name(moveName))
    tasks = []
    for move in possibleMoves:
        tasks.append(asyncio.ensure_future(pokeapi_move_request(session, move)))
    returnPokemon.possibleMoves = await asyncio.gather(*tasks)
    timeEnd = time.time()
    timeTotal = timeEnd - timeStart

    # Fill known moves
    returnPokemon.knownMoves = fill_known_moves(returnPokemon, previousPokemon)

    # Find possible Dynamax moves
    tasks = []
    tasks.append(asyncio.ensure_future(get_max_moves(session, returnPokemon)))
    returnPokemon.maxMoves = await asyncio.gather(*tasks)
    returnPokemon.maxMoves = returnPokemon.maxMoves[0]

    logging.info('Searching for possible moves for ' + pokemon.name + ' in ' + str(timeTotal))
    returnPokemon.lookupPerformed = True

    return returnPokemon


# Fixes pokemon names/moves to submit to pokeapi.
def adjust_name(entry):
    specificCases = {
        'Aegislash': 'aegislash-blade',
        'Basculin': 'basculin-red-striped',
        'Darmanitan': 'darmanitan-standard',
        'Darmanitan-Galar': 'darmanitan-galar-standard',
        'Darmanitan-Galar-Zen': 'darmanitan-galar-zen',
        'Eiscue': 'eiscue-ice',
        'Eiscue-Noice': 'eiscue-ice',
        'Gastrodon-East': 'gastrodon',
        'Genesect-Douse': 'genesect',
        'Giratina': 'giratina-altered',
        'Gourgeist': "gourgeist-average",
        'Indeedee': 'indeedee-male',
        'Indeedee-F': 'indeedee-female',
        'Keldeo': 'keldeo-ordinary',
        'Landorus': 'landorus-incarnate',
        'Lycanroc': 'lycanroc-midday',
        'Meowstic': 'meowstic-male',
        'Meowstic-F': 'meowstic-female',
        'Mimikyu': 'mimikyu-disguised',
        'Mimikyu-Busted': 'mimikyu-disguised',
        'Morpeko': 'morpeko-full-belly',
        'Necrozma-Dawn-Wings': 'necrozma-dawn',
        'Necrozma-Dusk-Mane': 'necrozma-dusk',
        'Thundurus': 'thundurus-incarnate',
        'Tornadus': 'tornadus-incarnate',
        'Toxtricity': 'toxtricity-amped',
        'Urshifu': 'urshifu-single-strike',
        'Urshifu-Gmax': 'urshifu-single-strike-gmax',
        'Wishiwashi': 'wishiwashi-school',
        'Zygarde': 'zygarde-50'
    }

    if re.search(r"Silvally", entry):
        return 'silvally'
    if re.search(r"Pikachu", entry):
        return 'pikachu'
    if entry in specificCases:
        return specificCases[entry]
    returnName = entry
    returnName = returnName.lower()
    returnName = returnName.replace("’", '')
    returnName = returnName.replace("'", '')
    returnName = returnName.replace('%', '')
    returnName = returnName.replace(' ', '-')
    returnName = returnName.replace('.', '')
    returnName = returnName.replace(':', '')
    return returnName


async def pokeapi_move_request(session, moveName):
    adjustedName = adjust_name(moveName)
    moveRequest = await session.get_move(adjustedName)
    return moveRequest


def get_sets_json_data():
    #setsFilePath = os.path.dirname(os.getcwd()) + '/teams/old_sets.json'
    setsFile = open('teams/old_sets.json', 'r')
    allSets = json.load(setsFile)
    setsFile.close()
    return allSets


# Updates a pokemon's effective stats based on various conditions
def calculate_effective_stats(pokemon, field, battleState):
    # Factor in boosts
    statBoostModifiers = {
        6: 4,
        5: 3.5,
        4: 3,
        3: 2.5,
        2: 2,
        1: 1.5,
        0: 1,
        -1: .67,
        -2: .5,
        -3: .4,
        -4: .33,
        -5: .29,
        -6: .25
    }
    if pokemon.isDynamaxed:
        pokemon.effectiveStats['HP'] = pokemon.leveledStats['HP'] * 2
    else:
        pokemon.effectiveStats['HP'] = pokemon.leveledStats['HP']
    pokemon.effectiveStats['Atk'] = \
        pokemon.leveledStats['Atk'] * statBoostModifiers[pokemon.boosts['Atk']]
    pokemon.effectiveStats['Def'] = \
        pokemon.leveledStats['Def'] * statBoostModifiers[pokemon.boosts['Def']]
    pokemon.effectiveStats['Spa'] = \
        pokemon.leveledStats['Spa'] * statBoostModifiers[pokemon.boosts['Spa']]
    pokemon.effectiveStats['SpD'] = \
        pokemon.leveledStats['SpD'] * statBoostModifiers[pokemon.boosts['SpD']]
    pokemon.effectiveStats['Spe'] = \
        pokemon.leveledStats['Spe'] * statBoostModifiers[pokemon.boosts['Spe']]
    if field['tailwind']['isUp']:
        pokemon.effectiveStats['Spe'] *= 2

    # Factor in status condition
    if pokemon.statusCondition == 'PAR':
        pokemon.effectiveStats['Spe'] *= .5

    # Factor in items
    if 'Choice Band' in pokemon.item:
        pokemon.effectiveStats['Atk'] *= 1.5
    elif 'Choice Specs' in pokemon.item:
        pokemon.effectiveStats['Spa'] *= 1.5
    elif 'Choice Scarf' in pokemon.item:
        pokemon.effectiveStats['Spe'] *= 1.5
    elif 'Assault Vest' in pokemon.item:
        pokemon.effectiveStats['SpD'] *= 1.5
    elif 'Eviolite' in pokemon.item:
        pokemon.effectiveStats['Def'] *= 1.5
        pokemon.effectiveStats['SpD'] *= 1.5

    # Factor in abilities
    if 'Chlorophyll' in pokemon.ability and battleState.weather['type'] == 'Sun':
        pokemon.effectiveStats['Spe'] *= 1.5
    elif 'Swift Swim' in pokemon.ability and battleState.weather['type'] == 'Rain':
        pokemon.effectiveStats['Spe'] *= 1.5
    elif 'Slush Rush' in pokemon.ability and battleState.weather['type'] == 'Hail':
        pokemon.effectiveStats['Spe'] *= 1.5
    elif 'Sand Rush' in pokemon.ability and battleState.weather['type'] == 'Sand':
        pokemon.effectiveStats['Spe'] *= 1.5
    elif 'Huge Power' in pokemon.ability:
        pokemon.effectiveStats['Atk'] *= 2
    elif 'Marvel Scale' in pokemon.ability and pokemon.statusCondition is not None:
        pokemon.effectiveStats['Def'] *= 1.5
    elif 'Fur Coat' in pokemon.ability:
        pokemon.effectiveStats['Def'] *= 2

    # Factor dynamax
    if pokemon.isDynamaxed:
        pokemon.effectiveStats['HP'] = pokemon.leveledStats['HP'] * 2
