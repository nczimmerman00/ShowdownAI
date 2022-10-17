import logging
from copy import deepcopy
import numpy as np
import pandas as pd
#from webInterface import get_pokemon_index, adjust_name,  BattleState, calculate_effective_stats
import webInterface


class OutcomeNode:
    def __init__(self, parent, probability, split_reason):
        # If root node
        if isinstance(parent, webInterface.BattleState):
            self.battleState = parent
            self.parent = None
            self.probability = probability
            self.mySelectedOption = None
            self.opponentSelectedOption = None
        elif isinstance(parent, OutcomeNode):
            self.parent = parent
            self.battleState = deepcopy(parent.battleState)
            parent.addChild(self)
            self.probability = probability * parent.probability  # Range between 0 and 1
            self.mySelectedOption = parent.mySelectedOption
            self.opponentSelectedOption = parent.opponentSelectedOption
        self.children = []
        if probability > 1:
            self.probability = 1
        elif probability < 0:
            self.probability = 0
        self.endNode = False
        self.frozen = False
        self.score = None
        self.myForcedSwitch = False
        self.forcedSwitchChoice = None
        self.opponentForcedSwitch = False
        self.split_reason = split_reason

    def addChild(self, childOutcome):
        self.children.append(childOutcome)

    def get_children(self):
        if not self.children:
            return [self]
        returnList = []
        for child in self.children:
            returnList += child.get_children()
        return returnList

    def get_non_end_children(self):
        if not self.children:
            if not self.endNode:
                return [self]
            else:
                return []
        returnList = []
        for child in self.children:
            childNodes = child.get_non_end_children()
            returnList += childNodes
        return returnList

    def get_non_frozen_children(self):
        if not self.children:
            if not self.frozen and not self.endNode:
                return [self]
            else:
                return []
        returnList = []
        for child in self.children:
            childNodes = child.get_non_frozen_children()
        returnList += childNodes
        return returnList

    def freeze_node(self):
        self.frozen = True

    def unfreeze_nodes(self):
        self.frozen = False
        for child in self.children:
            child.unfreeze_nodes()

    def set_as_endNode(self):
        self.endNode = True

    def set_my_forced_switch(self):
        self.myForcedSwitch = True

    def set_opponent_forced_switch(self):
        self.opponentForcedSwitch = True

    def set_score(self, rating):
        self.score = rating

    def set_my_selected_option(self, option):
        self.mySelectedOption = option

    def set_oppponent_selected_option(self, option):
        self.opponentSelectedOption = option


# Takes an outcome object, and returns the best perceived possible outcome for the current turn
def decide_option(outcome, turn_depth, prediction_function, scalar):
    myPossibleOptions = []
    opponentPossibleOptions = []
    # Check if myself or opponent needs to switch in and look at possible switch options
    if not outcome.battleState.myTeam[outcome.battleState.myLeadIndex].inBattle:
        # Get possible switch options
        switch_options = check_for_switch_options(outcome.battleState.myTeam, outcome.battleState.myLeadIndex)
        # If I have no lead, and no switch options, I've lost
        if not switch_options:
            outcome.set_score(0)
            return [outcome]
        opponentLead = outcome.battleState.opponentTeam[outcome.battleState.opponentLeadIndex]
        switch_options = switches_to_consider(switch_options, opponentLead, opponentLead.possibleMoves)
        for option in switch_options:
            optionTuple = (None, webInterface.get_pokemon_index(outcome.battleState.myTeam, option.name))
            myPossibleOptions.append(optionTuple)

        # Find the best possible switch
        possibleOutcomes = []
        for myOption in myPossibleOptions:
            newNode = OutcomeNode(outcome, 1, 'My forced switch. Index: ' + str(myOption[1]))
            newNode.set_my_selected_option(myOption)
            simulate_switch(newNode, True, myOption[1])
            possibleOutcomes.append(decide_option(newNode, turn_depth - 1, prediction_function, scalar)[0])
        for possibleOutcome in possibleOutcomes:
            calculate_score(possibleOutcome, prediction_function, scalar)
        mySelectedOutcome = get_best_case(possibleOutcomes)
        # Remove the other options from the children list
        mySelectedOutcome.parent.children = [mySelectedOutcome]
        return [mySelectedOutcome]

    if not outcome.battleState.opponentTeam[outcome.battleState.opponentLeadIndex].inBattle:
        # Get known possible switch options
        switch_options = check_for_switch_options(outcome.battleState.opponentTeam, outcome.battleState.opponentLeadIndex)
        optionIndex = 0
        endPoint = len(switch_options)
        while optionIndex < endPoint:
            if not switch_options[optionIndex].isRevealed:
                switch_options.remove(switch_options[optionIndex])
                endPoint -= 1
            else:
                optionIndex += 1
        # If opponent has no lead, and no switch options, I've won
        if not switch_options:
            outcome.set_score(1)
            return [outcome]
        for option in switch_options:
            optionTuple = (None, webInterface.get_pokemon_index(outcome.battleState.opponentTeam, option.name))
            opponentPossibleOptions.append(optionTuple)

        # Find the best possible switch
        possibleOutcomes = []
        for opponentOption in opponentPossibleOptions:
            newNode = OutcomeNode(outcome, 1, 'Opponent forced switch. Index: ' + str(opponentOption[1]))
            newNode.set_oppponent_selected_option(opponentOption)
            simulate_switch(newNode, False, opponentOption[1])
            possibleOutcomes.append(decide_option(newNode, turn_depth, prediction_function, scalar)[-1])
        for possibleOutcome in possibleOutcomes:
            calculate_score(possibleOutcome, prediction_function, scalar)
        opponentSelectedOutcome = get_worst_case(possibleOutcomes)
        opponentSelectedOutcome.parent.children = [opponentSelectedOutcome]
        return [opponentSelectedOutcome]

    # Terminal Condition
    if turn_depth <= 0:
        return [outcome]

    myLead = outcome.battleState.myTeam[outcome.battleState.myLeadIndex]
    opponentLead = outcome.battleState.opponentTeam[outcome.battleState.opponentLeadIndex]
    if outcome.battleState.myTeam[outcome.battleState.myLeadIndex].inBattle and \
            outcome.battleState.opponentTeam[outcome.battleState.opponentLeadIndex].inBattle:

        # Get my possible switches
        possibleSwitchOptions = check_for_switch_options(outcome.battleState.myTeam, outcome.battleState.myLeadIndex)
        for option in possibleSwitchOptions:
            optionTuple = (None, webInterface.get_pokemon_index(outcome.battleState.myTeam, option.name))
            myPossibleOptions.append(optionTuple)
        # Get my possible moves
        if myLead.isDynamaxed:
            for move in myLead.maxMoves:
                optionTuple = (move, None)
                myPossibleOptions.append(optionTuple)
        elif myLead.item in ['Choice Band', 'Choice Scarf', 'Choice Specs'] and \
                myLead.lastUsedMove is not None:
            optionTuple = (get_move(myLead.knownMoves, webInterface.adjust_name(myLead.lastUsedMove)), None)
            myPossibleOptions.append(optionTuple)
        else:
            move_list = attacks_to_consider(outcome, myLead.knownMoves, myLead, opponentLead)
            for move in move_list:
                '''
                if move.name in ['u-turn', 'flip-turn', 'volt-switch']:
                    for option in possibleSwitchOptions:
                        optionTuple = (move, get_pokemon_index(outcome.battleState.myTeam, option.name))
                        myPossibleOptions.append(optionTuple)
                else:
                '''
                optionTuple = (move, None)
                myPossibleOptions.append(optionTuple)
        if outcome.battleState.myDynamaxAvailable and myLead.name not in ['Zacian', 'Zacian-Crowned', 'Zamazenta',
                                                                          'Zamazenta-Crowned', 'Eternatus'] \
                and len(outcome.battleState.opponentTeam) > 1:
            for move in myLead.maxMoves:
                optionTuple = (move, None)
                myPossibleOptions.append(optionTuple)

        # Get opponent possible switches
        possibleSwitchOptions = check_for_switch_options(outcome.battleState.opponentTeam,
                                                         outcome.battleState.opponentLeadIndex)
        for option in possibleSwitchOptions:
            if option.isRevealed:
                optionTuple = (None, webInterface.get_pokemon_index(outcome.battleState.opponentTeam, option.name))
                opponentPossibleOptions.append(optionTuple)
        # Get opponent possible moves
        if len(opponentLead.knownMoves) < 4:
            opponentMoveList = opponentLead.possibleMoves
        else:
            opponentMoveList = opponentLead.knownMoves
        if opponentLead.isDynamaxed:
            for move in opponentLead.maxMoves:
                optionTuple = (move, None)
                opponentPossibleOptions.append(optionTuple)
        elif opponentLead.item in ['Choice Band', 'Choice Scarf', 'Choice Specs'] and \
                opponentLead.lastUsedMove is not None:
            optionTuple = (get_move(opponentMoveList, webInterface.adjust_name(opponentLead.lastUsedMove)), None)
            opponentPossibleOptions.append(optionTuple)
        else:
            opponentMoveList = attacks_to_consider(outcome, opponentMoveList, opponentLead, myLead)
            for move in opponentMoveList:
                '''
                if move.name in ['u-turn', 'flip-turn', 'volt-switch']:
                    for option in possibleSwitchOptions:
                        optionTuple = (move, get_pokemon_index(outcome.battleState.opponentTeam, option.name))
                        opponentPossibleOptions.append(optionTuple)
                else:
                '''
                optionTuple = (move, None)
                opponentPossibleOptions.append(optionTuple)

    # Calculate possible outcomes if no switch is needed
    myOptionOutcomes = []
    for myOption in myPossibleOptions:
        oppOptionOutcomes = []
        myChoice = OutcomeNode(outcome, 1, 'My Turn decision')
        myChoice.set_my_selected_option((myOption[0], myOption[1]))
        for opponentOption in opponentPossibleOptions:
            opponentChoice = OutcomeNode(myChoice, 1, 'Opponent Turn Decision')
            opponentChoice.set_oppponent_selected_option((opponentOption[0], opponentOption[1]))
            nodeList = simulate_turn(opponentChoice, myLead, opponentLead,
                                     myOption[0], opponentOption[0], myOption[1], opponentOption[1])
            possibleOutcomes = []
            for possibleOutcome in nodeList:
                possibleOutcomes.append(decide_option(possibleOutcome, turn_depth - 1, prediction_function, scalar)[0])
            # Calculate Outcome Scores
            for possibleOutcome in possibleOutcomes:
                calculate_score(possibleOutcome, prediction_function, scalar)
            # Get average score for possible outcomes
            opponentChoice.set_score(get_average_score(possibleOutcomes))
            oppOptionOutcomes.append(opponentChoice)
        # Determine best option for the opponent
        oppSelectedOptionScore = get_worst_outcome(oppOptionOutcomes)
        # Determine best option for myself
        myOptionOutcomes.append(oppSelectedOptionScore)
    sort_best_outcomes(myOptionOutcomes)
    return myOptionOutcomes


# Returns a list of OutcomeNode objects. myOption and opponentOption can be either a move object or switch index (int).
def simulate_turn(outcome, myPokemon, opponentPokemon, myOption, opponentOption, mySwitchIndex, opponentSwitchIndex):
    webInterface.calculate_effective_stats(myPokemon, outcome.battleState.myField, outcome.battleState)
    webInterface.calculate_effective_stats(opponentPokemon, outcome.battleState.opponentField, outcome.battleState)

    nodeList = outcome.get_non_end_children()
    for node in nodeList:
        # If max move was used, expend that player's dynamax
        if myOption:
            if 'max-' in myOption.name[:4]:
                node.battleState.expend_my_dynamax()
        if opponentOption:
            if 'max-' in opponentOption.name[:4]:
                node.battleState.expend_opponent_dynamax()

        myLead = node.battleState.myTeam[node.battleState.myLeadIndex]
        opponentLead = node.battleState.opponentTeam[node.battleState.opponentLeadIndex]
        webInterface.calculate_effective_stats(myLead, node.battleState.myField, node.battleState)
        webInterface.calculate_effective_stats(opponentLead, node.battleState.opponentField, node.battleState)
        # Determine turn order
        # If both players switch, turn order is determined based on speed.
        if myOption is None and mySwitchIndex is not None and \
                opponentOption is None and opponentSwitchIndex is not None:
            # Speed Tie Split
            if myLead.effectiveStats['Spe'] == opponentLead.effectiveStats['Spe']:
                # I win the speed tie
                newNode = OutcomeNode(node, .5, 'Speed tie')
                myLead = newNode.battleState.myTeam[newNode.battleState.myLeadIndex]
                opponentLead = newNode.battleState.myTeam[newNode.battleState.opponentLeadIndex]
                simulate_switch(newNode, True, mySwitchIndex)
                webInterface.calculate_effective_stats(myLead, newNode.battleState.myField, newNode.battleState)
                webInterface.calculate_effective_stats(opponentLead, newNode.battleState.opponentField, newNode.battleState)
                simulate_switch(newNode, False, opponentSwitchIndex)

                # Opponent wins the speed tie
                newNode = OutcomeNode(node, .5, 'Speed tie')
                myLead = newNode.battleState.myTeam[newNode.battleState.myLeadIndex]
                opponentLead = newNode.battleState.myTeam[newNode.battleState.opponentLeadIndex]
                simulate_switch(newNode, False, opponentSwitchIndex)
                webInterface.calculate_effective_stats(myLead, node.battleState.myField, node.battleState)
                webInterface.calculate_effective_stats(opponentLead, node.battleState.opponentField, node.battleState)
                simulate_switch(newNode, True, mySwitchIndex)
            # If I'm faster
            elif myLead.effectiveStats['Spe'] > opponentPokemon.effectiveStats['Spe']:
                simulate_switch(node, True, mySwitchIndex)
                webInterface.calculate_effective_stats(myLead, node.battleState.myField, node.battleState)
                webInterface.calculate_effective_stats(opponentLead, node.battleState.opponentField, node.battleState)
                simulate_switch(node, False, opponentSwitchIndex)
            # Opponent is faster
            else:
                simulate_switch(node, False, opponentSwitchIndex)
                webInterface.calculate_effective_stats(myLead, node.battleState.myField, node.battleState)
                webInterface.calculate_effective_stats(opponentLead, node.battleState.opponentField, node.battleState)
                simulate_switch(node, True, mySwitchIndex)
        # If I switch and opponent attacks, I go first
        elif myOption is None and mySwitchIndex is not None and opponentOption is not None:
            simulate_switch(node, True, mySwitchIndex)
            myLead = node.battleState.myTeam[node.battleState.myLeadIndex]
            opponentLead = node.battleState.opponentTeam[node.battleState.opponentLeadIndex]
            webInterface.calculate_effective_stats(myLead, node.battleState.myField, node.battleState)
            webInterface.calculate_effective_stats(opponentLead, node.battleState.opponentField, node.battleState)
            use_move(node, opponentLead, myLead, opponentOption, False, opponentSwitchIndex)
        # If I attack and opponent switches, opponent goes first
        elif myOption is not None and opponentOption is None and opponentSwitchIndex is not None:
            simulate_switch(node, False, opponentSwitchIndex)
            myLead = node.battleState.myTeam[node.battleState.myLeadIndex]
            opponentLead = node.battleState.opponentTeam[node.battleState.opponentLeadIndex]
            webInterface.calculate_effective_stats(myLead, node.battleState.myField, node.battleState)
            webInterface.calculate_effective_stats(opponentLead, node.battleState.opponentField, node.battleState)
            use_move(node, myLead, opponentLead, myOption, True, mySwitchIndex)
        # If both players attack, turn order is determined by move priority, and then speed.
        else:
            if 'Prankster' in myPokemon.ability and myOption.damage_class.name == 'status':
                myOption.priority += 1
            if 'Prankster' in opponentPokemon.ability and opponentOption.damage_class.name == 'status':
                opponentOption.priority += 1
            if myOption.priority == opponentOption.priority:
                # If I'm faster and trick room isn't active
                if (myLead.effectiveStats['Spe'] > opponentLead.effectiveStats['Spe'] and
                    not outcome.battleState.trickRoom['isUp'])\
                        or (myLead.effectiveStats['Spe'] < opponentLead.effectiveStats['Spe']
                            and outcome.battleState.trickRoom['isUp']):
                    use_move(node, myLead, opponentLead, myOption, True, mySwitchIndex)
                    myLead = node.battleState.myTeam[node.battleState.myLeadIndex]
                    opponentLead = node.battleState.opponentTeam[node.battleState.opponentLeadIndex]
                    webInterface.calculate_effective_stats(myLead, node.battleState.myField, node.battleState)
                    webInterface.calculate_effective_stats(opponentLead, node.battleState.opponentField, node.battleState)
                    use_move(node, opponentLead, myLead, opponentOption, False, opponentSwitchIndex)
                # If opponent is faster
                elif (myLead.effectiveStats['Spe'] < opponentLead.effectiveStats['Spe'] and not
                    outcome.battleState.trickRoom['isUp']) or (
                        myLead.effectiveStats['Spe'] < opponentLead.effectiveStats['Spe'] and
                            outcome.battleState['isUp']):
                    use_move(node, opponentLead, myLead, opponentOption, False, opponentSwitchIndex)
                    myLead = node.battleState.myTeam[node.battleState.myLeadIndex]
                    opponentLead = node.battleState.opponentTeam[node.battleState.opponentLeadIndex]
                    webInterface.calculate_effective_stats(myLead, node.battleState.myField, node.battleState)
                    webInterface.calculate_effective_stats(opponentLead, node.battleState.opponentField, node.battleState)
                    use_move(node, myLead, opponentLead, myOption, True, mySwitchIndex)
                # If speed tie
                else:
                    # I win the speed tie
                    newNode = OutcomeNode(node, .5, 'Speed Tie')
                    myLead = newNode.battleState.myTeam[newNode.battleState.myLeadIndex]
                    opponentLead = newNode.battleState.opponentTeam[newNode.battleState.opponentLeadIndex]
                    use_move(newNode, myLead, opponentLead, myOption, True, mySwitchIndex)
                    myLead = newNode.battleState.myTeam[newNode.battleState.myLeadIndex]
                    opponentLead = newNode.battleState.opponentTeam[newNode.battleState.opponentLeadIndex]
                    webInterface.calculate_effective_stats(myLead, newNode.battleState.myField, newNode.battleState)
                    webInterface.calculate_effective_stats(opponentLead, newNode.battleState.opponentField, newNode.battleState)
                    use_move(newNode, opponentLead, myLead, opponentOption, False, opponentSwitchIndex)

                    # Opponent wins the speed tie
                    newNode = OutcomeNode(node, .5, 'Speed Tie')
                    myLead = newNode.battleState.myTeam[newNode.battleState.myLeadIndex]
                    opponentLead = newNode.battleState.opponentTeam[newNode.battleState.opponentLeadIndex]
                    use_move(newNode, opponentLead, myLead, opponentOption, False, opponentSwitchIndex)
                    myLead = newNode.battleState.myTeam[newNode.battleState.myLeadIndex]
                    opponentLead = newNode.battleState.opponentTeam[newNode.battleState.opponentLeadIndex]
                    webInterface.calculate_effective_stats(myLead, newNode.battleState.myField, newNode.battleState)
                    webInterface.calculate_effective_stats(opponentLead, newNode.battleState.opponentField, newNode.battleState)
                    use_move(newNode, myLead, opponentLead, myOption, True, mySwitchIndex)
            elif myOption.priority > opponentOption.priority:
                use_move(node, myLead, opponentLead, myOption, True, mySwitchIndex)
                myLead = node.battleState.myTeam[node.battleState.myLeadIndex]
                opponentLead = node.battleState.opponentTeam[node.battleState.opponentLeadIndex]
                webInterface.calculate_effective_stats(myLead, node.battleState.myField, node.battleState)
                webInterface.calculate_effective_stats(opponentLead, node.battleState.opponentField, node.battleState)
                use_move(node, opponentLead, myLead, opponentOption, False, opponentSwitchIndex)
            else:
                use_move(node, opponentLead, myLead, opponentOption, False, opponentSwitchIndex)
                myLead = node.battleState.myTeam[node.battleState.myLeadIndex]
                opponentLead = node.battleState.opponentTeam[node.battleState.opponentLeadIndex]
                webInterface.calculate_effective_stats(myLead, node.battleState.myField, node.battleState)
                webInterface.calculate_effective_stats(opponentLead, node.battleState.opponentField, node.battleState)
                use_move(node, myLead, opponentLead, myOption, True, mySwitchIndex)

    # End of turn procedures
    nodeList = outcome.get_non_end_children()
    for node in nodeList:
        node.battleState.end_turn_procedure()

        myLead = node.battleState.myTeam[webInterface.get_pokemon_index(node.battleState.myTeam, myPokemon.name)]
        opponentLead = node.battleState.opponentTeam[
            webInterface.get_pokemon_index(node.battleState.opponentTeam, opponentPokemon.name)]
        # Set lastUsed move
        if myOption is not None:
            myLead.lastUsedMove = myOption.name
        if opponentOption is not None:
            opponentLead.lastUsedMove = opponentOption.name
        # Reset hasMoved for both pokemon
        myLead.hasMoved = False
        opponentLead.hasMoved = False
    return outcome.get_children()


# Returns list of potential outcomes after using a move
def use_move(outcome, attacker, defender, move, isMyAttack, attackSwitchIndex):
    logging.info('Calculating ' + attacker.name + ' using ' + move.name + ' against ' + defender.name)
    statusAbbreviation = {
        'burn': 'BRN',
        'sleep': 'SLP',
        'poison': 'PSN',
        'freeze': 'FRZ',
        'paralysis': 'PAR'
    }
    statAbbreviation = {
        'attack': 'Atk',
        'defense': 'Def',
        'special-attack': 'Spa',
        'special-defense': 'SpD',
        'speed': 'Spe',
        'accuracy': 'Acc'
    }
    # Check to make sure attacker isn't fainted
    if attacker.fainted:
        outcome.unfreeze_nodes()
        return outcome.get_children()

    # If defender is fainted, make sure attack doesn't target the defender.
    if defender.fainted and not (move.target.name == 'user' or move.target.name == 'entire-field'):
        outcome.unfreeze_nodes()
        return outcome.get_children()

    # If defender used protect, attack won't connect on the defender if targeted
    # (unless defender is not dynamaxed and attacker is)
    if defender.isProtected and ('Unseen Fist' not in attacker.ability and not defender.isDynamaxed):
        opponentTargeted = ['selected-pokemon', 'all-opponents', 'all-other-pokemon']
        if (defender.isDynamaxed or not attacker.isDynamaxed) and move.target.name in opponentTargeted:
            outcome.unfreeze_nodes()
            return outcome.get_children()

    attackerPokemon = find_pokemon(outcome.battleState, attacker.name, isMyAttack)
    # If the attacker is flinched, skip their turn
    if attackerPokemon.flinched:
        attackerPokemon.flinched = False
        outcome.unfreeze_nodes()
        return outcome.get_children()

    # If the attack is taunted or has an assault vest and a status move is used, skip their turn
    if ('Taunt' in attacker.volatileConditions or 'Assault Vest' in attacker.item)\
            and move.damage_class.name == 'status':
        outcome.unfreeze_nodes()
        return outcome.get_children()

    # If attacker is affected by paralysis, sleep, or freeze
    nodeList = outcome.get_non_end_children()
    for node in nodeList:
        if attacker.statusCondition == 'SLP':
            sleepChance = {
                0: 100,
                1: .667,
                2: .333,
                3: 0,
                4: 0,
                5: 0
            }
            # Attacker stays asleep
            try:
                newNode = OutcomeNode(node, sleepChance[attacker.sleepTurns], attacker.name + ' stayed asleep')
            except KeyError:
                newNode = OutcomeNode(node, 0, attacker.name + ' stayed asleep')
            newNode.freeze_node()
            attackerPokemon = find_pokemon(newNode.battleState, attacker.name, isMyAttack)
            try:
                attackerPokemon.sleepTurns += 1
            except TypeError:
                attackerPokemon.sleepTurns = 1
            # Attacker wakes up
            newNode = OutcomeNode(node, 1 - sleepChance[attacker.sleepTurns], attacker.name + ' woke up')
            attackerPokemon = find_pokemon(newNode.battleState, attacker.name, isMyAttack)
            attackerPokemon.statusCondition = None
            attackerPokemon.sleepTurns = 0
        elif attacker.statusCondition == 'PAR':
            # Attacker cannot move
            newNode = OutcomeNode(node, .25, attacker.name + " can't move due to paralysis")
            newNode.freeze_node()
            # Attacker can move
            OutcomeNode(node, .75, attacker.name + ' paralyzed, but moved')
        elif attacker.statusCondition == 'FRZ':
            newNode = OutcomeNode(node, .8, attacker.name + ' is frozen')
            newNode.freeze_node()
            newNode = OutcomeNode(node, .2, attacker.name + ' thawed out')
            attackerPokemon = find_pokemon(newNode.battleState, attacker.name, isMyAttack)
            attackerPokemon.statusCondition = None

    # If attacker is confused
    if 'Confused' in attacker.volatileConditions:
        # Chances to snap out of confusion for amount of turns spent confused
        confusionOdds = {
            0: 0,
            1: 0,
            2: .25,
            3: .5,
            4: .75,
            5: 1
        }
        nodeList = outcome.get_non_frozen_children()
        for node in nodeList:
            # Attacker gets out of confusion
            newNode = OutcomeNode(node, confusionOdds[attacker.confusionTurns], attacker.name +
                                  ' snapped out of confusion')
            attackerPokemon = find_pokemon(newNode.battleState, attacker.name, isMyAttack)
            attackerPokemon.remove_volatile_condition('Confused')
            attackerPokemon.confusionTurns = 0
            # Attacker attacks through confusion
            newNode = OutcomeNode(node, confusionOdds[attackerPokemon.confusionTurns] * .667,
                                  attacker.name + ' attacked through confusion')
            attackerPokemon = find_pokemon(newNode.battleState, attacker.name, isMyAttack)
            attackerPokemon.confusionTurns += 1
            # Attacker hits itself through confusion
            try:
                newNode = OutcomeNode(node, confusionOdds[attackerPokemon.confusionTurns] * .333,
                                    attacker.name + ' hit itself in confusion')
            except KeyError:
                newNode = OutcomeNode(node, .3, attacker.name + ' hit itself in confusion')
            newNode.freeze_node()
            attackerPokemon = find_pokemon(newNode.battleState, attacker.name, isMyAttack)
            damage = calculate_confusion_damage(attackerPokemon)
            attackerPokemon.take_damage(damage)

    # No guard skips all accuracy checks
    if 'No Guard' in attacker.ability or 'No Guard' in defender.ability:
        move.accuracy = 100

    # Create outcome child node if accuracy is not 100/null
    if move.accuracy is not None and move.accuracy != 100:
        nodeList = outcome.get_non_frozen_children()
        for node in nodeList:
            # If the attack misses
            newNode = OutcomeNode(node, (100 - move.accuracy) * .01,
                                  attacker.name + ' missed their attack')
            newNode.freeze_node()
            if move.name == 'high-jump-kick':
                if isMyAttack:
                    attackerIndex = webInterface.get_pokemon_index(newNode.battleState.myTeam, attacker.name)
                    myAttacker = newNode.battleState.myTeam[attackerIndex]
                    myAttacker.take_damage(myAttacker.effectiveStats['HP'] / 2)
                else:
                    attackerIndex = webInterface.get_pokemon_index(newNode.battleState.opponentTeam, attacker.name)
                    theirAttacker = newNode.battleState.opponentTeam[attackerIndex]
                    theirAttacker.take_damage(theirAttacker.effectiveStats['HP'] / 2)
            OutcomeNode(node, move.accuracy * .01, attacker.name + ' hit their attack')

    # If the attack is a status move and doesn't miss
    if move.damage_class.name == 'status':
        # Dark type pokemon are immune to prankster
        if 'Prankster' in attacker.ability and 'dark' in defender.type:
            outcome.unfreeze_nodes()
            return outcome.get_children()
        nodeList = outcome.get_non_frozen_children()
        for node in nodeList:
            # Get defender and attacker from node
            attackerPokemon = find_pokemon(node.battleState, attacker.name, isMyAttack)
            defenderPokemon = find_pokemon(node.battleState, defender.name, not isMyAttack)
            if isMyAttack:
                defenderField = node.battleState.opponentField
                attackerField = node.battleState.myField
            else:
                defenderField = node.battleState.myField
                attackerField = node.battleState.opponentField

            # Toxic
            if move.name == 'toxic':
                defenderPokemon.set_status_condition('TOX')
            # If move inflicts status condition
            elif move.meta.ailment.name != 'none':
                if move.meta.ailment.name in statusAbbreviation:
                    defenderPokemon.set_status_condition(statusAbbreviation[move.meta.ailment.name])
                else:
                    defenderPokemon.add_volatile_condition(move.meta.ailment.name)

            # If move adjusts stats
            if move.stat_changes:
                for stat in move.stat_changes:
                    attackerPokemon.boost_stat(statAbbreviation[stat.stat.name], stat.change)

            # If the attack heals
            if move.meta.healing > 0:
                attacker.heal(attacker.leveledStats['HP'] * move.meta.healing * .01)

            # Special cases
            elif move.name in ['protect', 'detect', 'kings-shield', 'baneful-bunker', 'spiky-shield', 'max-guard']:
                if defenderPokemon.lastUsedMove in ['protect', 'detect', 'kings-shield', 'baneful-bunker', 'spiky-shield',
                                             'max-guard']:
                    # Protect fails
                    newNode = OutcomeNode(node, .5, attacker.name + ' failed their protect')
                    # Protect succeeds
                    newNode = OutcomeNode(node, .5, attacker.name + ' protected')
                    if isMyAttack:
                        attackerPokemon = newNode.battleState.myTeam[
                            webInterface.get_pokemon_index(newNode.battleState.myTeam, attacker.name)]
                    else:
                        attackerPokemon = newNode.battleState.opponentTeam[
                            webInterface.get_pokemon_index(newNode.battleState.opponentTeam, attacker.name)]
                attackerPokemon.isProtected = True
            elif move.name == 'taunt':
                defender.add_volatile_condition('Taunt')
            elif move.name == 'wish':
                pass
                if isMyAttack and node.battleState.turnsUntilMyWish == 0:
                    node.battleState.turnsUntilMyWish = 2
                elif not isMyAttack and node.battleState.turnsUntilOpponentWish == 0:
                    node.battleState.turnsUntilOpponentWish = 2
            elif move.name == 'encore':
                defender.add_volatile_condition('Encore')
            elif move.name == 'substitute':
                if attackerPokemon.substituteHP == 0 and attacker.hp > 25:
                    attackerPokemon.hp -= 25
                    attackerPokemon.substituteHP = 25
            elif move.name == 'heal-bell':
                if isMyAttack:
                    team = node.battleState.myTeam
                else:
                    team = node.battleState.opponentTeam
                for member in team:
                    member.statusCondition = None
            elif move.name == 'leech-seed':
                defender.add_volatile_condition('Leech Seed')
            elif move.name in ['trick', 'Switcheroo']:
                tempItem = attackerPokemon.item
                attackerPokemon.item = defenderPokemon.item
                defenderPokemon.item = tempItem
            elif move.name == 'curse':
                attackerPokemon.boost_stat('Spe', -1)
                attackerPokemon.boost_stat('Atk', 1)
                attackerPokemon.boost_stat('Def', 1)
            elif move.name == 'trick-room':
                node.battleState.set_trick_room()
            elif move.name == 'belly-drum':
                if attackerPokemon.hp > 50 and attackerPokemon.boosts['Atk'] != 6:
                    attackerPokemon.boost_stat('Atk', 12)
                    attackerPokemon.hp -= 50
            elif move.name == 'aurora-veil':
                if node.battleState.weather == 'Hail':
                    if isMyAttack:
                        node.battleState.myField['auroraVeil']['isUp'] = True
                        node.battleState.myField['auroraVeil']['minTurns'] = 5
                        node.battleState.myField['auroraVeil']['maxTurns'] = 5
                    else:
                        node.battleState.opponentField['auroraVeil']['isUp'] = True
                        node.battleState.opponentField['auroraVeil']['minTurns'] = 5
                        node.battleState.opponentField['auroraVeil']['maxTurns'] = 5
            elif move.name == 'reflect':
                if isMyAttack:
                    node.battleState.myField['reflect']['isUp'] = True
                    node.battleState.myField['reflect']['minTurns'] = 5
                    node.battleState.myField['reflect']['maxTurns'] = 5
                else:
                    node.battleState.opponentField['reflect']['isUp'] = True
                    node.battleState.opponentField['reflect']['minTurns'] = 5
                    node.battleState.opponentField['reflect']['maxTurns'] = 5
            elif move.name == 'light-screen':
                if isMyAttack:
                    node.battleState.myField['lightScreen']['isUp'] = True
                    node.battleState.myField['lightScreen']['minTurns'] = 5
                    node.battleState.myField['lightScreen']['maxTurns'] = 5
                else:
                    node.battleState.opponentField['lightScreen']['isUp'] = True
                    node.battleState.opponentField['lightScreen']['minTurns'] = 5
                    node.battleState.opponentField['lightScreen']['maxTurns'] = 5
            elif move.name == 'stealth-rock':
                if 'Stealth Rock' not in defenderField['entryHazards']:
                    defenderField['entryHazards'].append('Stealth Rock')
            elif move.name == 'spikes':
                if 'Spikes' not in defenderField['entryHazards']:
                    defenderField['entryHazards'].append('Spikes')
            elif move.name == 'sticky-web':
                if 'Sticky Web' not in defenderField['entryHazards']:
                    defenderField['entryHazards'].append('Sticky Web')
            elif move.name == 'toxic-spikes':
                if 'Toxic Spikes' not in defenderField['entryHazards']:
                    defenderField['entryHazards'].append('Toxic Spikes')
            elif move.name == 'rain-dance':
                node.battleState.set_weather('Rain')

            outcome.unfreeze_nodes()
            return outcome.get_children()

    # Poltergeist fails if defender has no item
    if len(defender.item) == 0:
        outcome.unfreeze_nodes()
        return outcome.get_children()

    # Moves that can only be used on the first turn the pokemon is out
    if move.name in ['fake-out', 'first-impression']:
        if attacker.lastUsedMove is not None:
            outcome.unfreeze_nodes()
            return outcome.get_children()

    # Temporary solution for solar moves
    if move.name in ['solar-beam', 'solar-blade'] and outcome.battleState.weather['type'] != 'Sun':
        outcome.unfreeze_nodes()
        return outcome.get_children()

    # If the attack doesn't miss
    nodeList = outcome.get_non_frozen_children()
    for node in nodeList:
        if move.damage_class.name != 'status':
            # Calculate crit chance
            crit_rate = {
                0: .0417,
                1: .125,
                2: .5,
                3: 1,
                4: 1,
                5: 1,
                6: 1,
                7: 1
            }
            crit_stage = move.meta.crit_rate
            if 'Scope Lens' in attacker.item:
                crit_stage += 1
            # # If attack crits
            # newNode = OutcomeNode(node, crit_rate[crit_stage], attacker.name + ' crit')
            # if isMyAttack:
            #     damage = calculate_damage(attacker, defender, move, True, newNode.battleState.opponentField,
            #                               newNode.battleState)
            #     defenderIndex = get_pokemon_index(newNode.battleState.opponentTeam, defender.name)
            #     attackerIndex = get_pokemon_index(newNode.battleState.myTeam, attacker.name)
            #     newNode.battleState.opponentTeam[defenderIndex].take_damage(damage)
            #     if move.meta.drain > 0:
            #         newNode.battleState.myTeam[attackerIndex].heal(damage * move.meta.drain * .01)
            #     if move.meta.drain < 0:
            #         recoil = damage * abs(move.meta.drain * .01)
            #         newNode.battleState.myTeam[attackerIndex].take_damage(recoil)
            #     if 'Life Orb' in newNode.battleState.myTeam[attackerIndex].item \
            #             and not newNode.battleState.myTeam[attackerIndex].isDynamaxed:
            #         newNode.battleState.myTeam[attackerIndex].take_life_orb_recoil()
            # else:
            #     damage = calculate_damage(attacker, defender, move, True, newNode.battleState.myField,
            #                               newNode.battleState)
            #     defenderIndex = get_pokemon_index(newNode.battleState.myTeam, defender.name)
            #     attackerIndex = get_pokemon_index(newNode.battleState.opponentTeam, attacker.name)
            #     newNode.battleState.myTeam[defenderIndex].take_damage(damage)
            #     if move.meta.drain > 0:
            #         newNode.battleState.opponentTeam[attackerIndex].heal(damage * move.meta.drain * .01)
            #     if move.meta.drain < 0:
            #         recoil = damage * abs(move.meta.drain * .01)
            #         newNode.battleState.opponentTeam[attackerIndex].take_damage(recoil)
            #     if 'Life Orb' in newNode.battleState.opponentTeam[attackerIndex].item \
            #             and not newNode.battleState.opponentTeam[attackerIndex].isDynamaxed:
            #         newNode.battleState.opponentTeam[attackerIndex].take_life_orb_recoil()

            # If attack doesn't crit
            # newNode = OutcomeNode(node, 1 - crit_rate[crit_stage], attacker.name + " didn't crit")
            newNode = node
            if isMyAttack:
                damage = calculate_damage(attacker, defender, move, False, newNode.battleState.opponentField,
                                          newNode.battleState)
                defenderIndex = webInterface.get_pokemon_index(newNode.battleState.opponentTeam, defender.name)
                attackerIndex = webInterface.get_pokemon_index(newNode.battleState.myTeam, attacker.name)
                newNode.battleState.opponentTeam[defenderIndex].take_damage(damage)
                if move.meta.drain > 0:
                    newNode.battleState.myTeam[attackerIndex].heal(damage * move.meta.drain * .01)
                if move.meta.drain < 0:
                    recoil = damage * abs(move.meta.drain * .01)
                    newNode.battleState.myTeam[attackerIndex].take_damage(recoil)
                if 'Life Orb' in newNode.battleState.myTeam[attackerIndex].item \
                        and not newNode.battleState.myTeam[attackerIndex].isDynamaxed:
                    newNode.battleState.myTeam[attackerIndex].take_life_orb_recoil()
            else:
                damage = calculate_damage(attacker, defender, move, False, newNode.battleState.myField,
                                          newNode.battleState)
                defenderIndex = webInterface.get_pokemon_index(newNode.battleState.myTeam, defender.name)
                attackerIndex = webInterface.get_pokemon_index(newNode.battleState.opponentTeam, attacker.name)
                newNode.battleState.myTeam[defenderIndex].take_damage(damage)
                if move.meta.drain > 0:
                    newNode.battleState.opponentTeam[attackerIndex].heal(damage * move.meta.drain * .01)
                if move.meta.drain < 0:
                    recoil = damage * abs(move.meta.drain * .01)
                    newNode.battleState.opponentTeam[attackerIndex].take_damage(recoil)
                if 'Life Orb' in newNode.battleState.opponentTeam[attackerIndex].item \
                        and not newNode.battleState.opponentTeam[attackerIndex].isDynamaxed:
                    newNode.battleState.opponentTeam[attackerIndex].take_life_orb_recoil()

    # If the attack can inflict a status
    if move.meta.ailment_chance > 0:
        nodeList = outcome.get_non_frozen_children()
        for node in nodeList:
            # Move inflicts status
            newNode = OutcomeNode(node, move.meta.ailment_chance * .01,
                                  attacker.name + "'s " + move.name + ' inflicted status')
            if isMyAttack:
                defenderIndex = webInterface.get_pokemon_index(newNode.battleState.opponentTeam, defender.name)
                if move.meta.ailment.name in statusAbbreviation:
                    newNode.battleState.opponentTeam[defenderIndex]\
                        .set_status_condition(statusAbbreviation[move.meta.ailment.name])
                else:
                    newNode.battleState.opponentTeam[defenderIndex].add_volatile_condition(move.meta.ailment.name)
            else:
                defenderIndex = webInterface.get_pokemon_index(newNode.battleState.myTeam, defender.name)
                if move.meta.ailment.name in statusAbbreviation:
                    newNode.battleState.myTeam[defenderIndex] \
                        .set_status_condition(statusAbbreviation[move.meta.ailment.name])
                else:
                    newNode.battleState.myTeam[defenderIndex].add_volatile_condition(move.meta.ailment.name)
            # Move doesn't inflict status
            newNode = OutcomeNode(node, (100 - move.meta.ailment_chance) * .01,
                                  attacker.name + "'s " + move.name + " didn't inflict side effect status")

    # If the attack can flinch
    if move.meta.flinch_chance > 0 and not defender.hasMoved:
        nodeList = outcome.get_non_frozen_children()
        for node in nodeList:
            # Move flinches
            newNode = OutcomeNode(node, move.meta.flinch_chance * .01,
                                  move.name + ' caused ' + defender.name + ' to flinch')
            if isMyAttack:
                defenderIndex = webInterface.get_pokemon_index(newNode.battleState.opponentTeam, defender.name)
                if newNode.battleState.opponentTeam[defenderIndex].substituteHP == 0 and \
                        'Inner Focus' not in defender.ability:
                    newNode.battleState.opponentTeam[defenderIndex].flinched = True
            else:
                defenderIndex = webInterface.get_pokemon_index(newNode.battleState.myTeam, defender.name)
                if newNode.battleState.myTeam[defenderIndex].substituteHP == 0 and \
                        'Inner Focus' not in defender.ability:
                    newNode.battleState.myTeam[defenderIndex].flinched = True
            # Move doesn't flinch
            newNode = OutcomeNode(node, (100 - move.meta.flinch_chance) * .01,
                                  attacker.name + "'s " + move.name + " didn't flinch")

    # If the attack adjusts stats
    if move.stat_changes:
        nodeList = outcome.get_non_frozen_children()
        for node in nodeList:
            # Stat change happens
            newNode = OutcomeNode(node, move.effect_chance * .01,
                                  attacker.name + "'s " + move.name + ' caused a stat change')
            if move.meta.category.name == 'damage+raise':
                if isMyAttack:
                    target = newNode.battleState.myTeam[webInterface.get_pokemon_index(newNode.battleState.myTeam, attacker.name)]
                else:
                    target = newNode.battleState.opponentTeam[webInterface.get_pokemon_index(
                        newNode.battleState.opponentTeam, attacker.name)]
            else:
                if isMyAttack:
                    target = newNode.battleState.opponentTeam[webInterface.get_pokemon_index(
                        newNode.battleState.opponentTeam, defender.name)]
                else:
                    target = newNode.battleState.myTeam[webInterface.get_pokemon_index(newNode.battleState.myTeam, defender.name)]
            for stat in move.stat_changes:
                target.boost_stat(statAbbreviation[stat.stat.name], stat.change)

            # Stat change doesn't happen
            newNode = OutcomeNode(node, (100 - move.effect_chance) * .01,
                                  attacker.name + "'s " + move.name + " didn't cause stat change")

    # If the attack is a max attack
    if attacker.isDynamaxed:
        nodeList = outcome.get_non_frozen_children()
        for node in nodeList:
            if isMyAttack:
                attackerPokemon = node.battleState.myTeam[node.battleState.myLeadIndex]
                defenderPokemon = node.battleState.opponentTeam[node.battleState.opponentLeadIndex]
            else:
                attackerPokemon = node.battleState.opponentTeam[node.battleState.opponentLeadIndex]
                defenderPokemon = node.battleState.myTeam[node.battleState.myLeadIndex]
            if move.name == 'max-strike':
                defenderPokemon.boost_stat('Spe', -1)
            elif move.name == 'max-knuckle':
                attackerPokemon.boost_stat('Atk', 1)
            elif move.name == 'max-airstream':
                attackerPokemon.boost_stat('Spe', 1)
            elif move.name == 'max-ooze':
                attackerPokemon.boost_stat('Spa', 1)
            elif move.name == 'max-quake':
                attackerPokemon.boost_stat('SpD', 1)
            elif move.name == 'max-rockfall':
                node.battleState.set_weather('Sandstorm')
            elif move.name == 'max-flutterby':
                defenderPokemon.boost_stat('Spa', -1)
            elif move.name == 'max-phantasm':
                defenderPokemon.boost_stat('Def', -1)
            elif move.name == 'max-steelspike':
                attackerPokemon.boost_stat('Def', 1)
            elif move.name == 'max-flare':
                node.battleState.set_weather('Sun')
            elif move.name == 'max-geyser':
                node.battleState.set_weather('Rain')
            elif move.name == 'max-overgrowth':
                node.battleState.set_terrain('Grassy Terrain')
            elif move.name == 'max-lightning':
                node.battleState.set_terrain('Electric Terrain')
            elif move.name == 'max-mindstorm':
                node.battleState.set_terrain('Psychic Terrain')
            elif move.name == 'max-hailstorm':
                node.battleState.set_weather('Hail')
            elif move.name == 'max-wyrmwind':
                defenderPokemon.boost_stat('Atk', -1)
            elif move.name == 'max-starfall':
                node.battleState.set_terrain('Misty Terrain')
            # TODO factor in gmax effects

    # Specific move cases
    nodeList = outcome.get_non_frozen_children()
    if move.name == 'rapid-spin':
        for node in nodeList:
            if isMyAttack:
                node.battleState.myField['entryHazards'] = []
            else:
                node.battleState.opponentField['entryHazards'] = []
    elif move.name in ['outrage', 'petal-dance']:
        if attacker.lastUsedMove == move.name and 'Confused' not in attacker.volatileConditions:
            for node in nodeList:
                # Outrage doesn't confuse
                OutcomeNode(node, .5, attacker.name + "'s " + move.name + " didn't confuse")
                # Outrage does confuse
                newNode = OutcomeNode(node, .5, attacker.name + "'s " + move.name + " caused confusion")
                attackerPokemon = find_pokemon(newNode.battleState, attacker.name, isMyAttack)
                if 'Confused' not in attacker.volatileConditions:
                    attacker.add_volatile_condition('Confused')
    '''
    elif move.name in ['u-turn', 'flip-turn', 'volt-switch']:
        for node in nodeList:
            simulate_switch(node, isMyAttack, attackSwitchIndex)
    '''

    # Set hasMoved on the attacker
    nodeList = outcome.get_non_frozen_children()
    for node in nodeList:
        if isMyAttack:
            attackerPokemon = node.battleState.myTeam[node.battleState.myLeadIndex]
        else:
            attackerPokemon = node.battleState.opponentTeam[node.battleState.opponentLeadIndex]
        attackerPokemon.hasMoved = True

    outcome.unfreeze_nodes()
    return outcome.get_children()


# Returns True if switch is possible. Returns False otherwise
def simulate_switch(outcome, isMySwitch, index):
    if isMySwitch:
        if outcome.battleState.myTeam[index].fainted:
            raise Exception("Can't switch to fainted pokemon. " + outcome.battleState.myTeam[index])
        outcome.battleState.my_switch(index)
        return True
    else:
        if outcome.battleState.opponentTeam[index].fainted:
            raise Exception("Can't switch to fainted pokemon. " + outcome.battleState.opponentTeam[index])
        outcome.battleState.opponent_switch(index)
        return True


# Returns list of possible switch options
def check_for_switch_options(team, lead_index):
    returnList = []
    for member in range(len(team)):
        if (not team[member].fainted) and (not team[member].inBattle) and (member != lead_index):
            returnList.append(team[member])
    return returnList


# Returns amount of damage (as a #) dealt by an attack
def calculate_damage(attacker, defender, attack, isCrit, defenderField, battleState):

    typeChart = {
        'normal': {'normal': 1, 'fighting': 1, 'flying': 1, 'poison': 1, 'ground': 1, 'rock': .5, 'bug': 1, 'ghost': 0,
                   'steel': .5, 'fire': 1, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': 1, 'ice': 1, 'dragon': 1,
                   'dark': 1, 'fairy': 1},
        'fighting': {'normal': 2, 'fighting': 1, 'flying': .5, 'poison': .5, 'ground': 1, 'rock': 2, 'bug': .5, 'ghost': 0,
                   'steel': 2, 'fire': 1, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': .5, 'ice': 2, 'dragon': 1,
                   'dark': 2, 'fairy': .5},
        'flying': {'normal': 1, 'fighting': 2, 'flying': 1, 'poison': 1, 'ground': 1, 'rock': .5, 'bug': 2, 'ghost': 1,
                   'steel': .5, 'fire': 1, 'water': 1, 'grass': 2, 'electric': .5, 'psychic': 1, 'ice': 1, 'dragon': 1,
                   'dark': 1, 'fairy': 1},
        'poison': {'normal': 1, 'fighting': 1, 'flying': 1, 'poison': .5, 'ground': .5, 'rock': .5, 'bug': 1, 'ghost': .5,
                   'steel': 0, 'fire': 1, 'water': 1, 'grass': 2, 'electric': 1, 'psychic': 1, 'ice': 1, 'dragon': 1,
                   'dark': 1, 'fairy': 2},
        'ground': {'normal': 1, 'fighting': 1, 'flying': 0, 'poison': 2, 'ground': 1, 'rock': 2, 'bug': .5, 'ghost': 1,
                   'steel': 2, 'fire': 2, 'water': 1, 'grass': .5, 'electric': 2, 'psychic': 1, 'ice': 1, 'dragon': 1,
                   'dark': 1, 'fairy': 1},
        'rock': {'normal': 1, 'fighting': .5, 'flying': 2, 'poison': 1, 'ground': .5, 'rock': .5, 'bug': 2, 'ghost': 1,
                   'steel': .5, 'fire': 2, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': 1, 'ice': 2, 'dragon': 1,
                   'dark': 1, 'fairy': 1},
        'bug': {'normal': 1, 'fighting':.5, 'flying': .5, 'poison': .5, 'ground': 1, 'rock': 1, 'bug': 1, 'ghost': .5,
                   'steel': .5, 'fire': .5, 'water': 1, 'grass': 2, 'electric': 1, 'psychic': 2, 'ice': 1, 'dragon': 1,
                   'dark': 2, 'fairy': .5},
        'ghost': {'normal': 0, 'fighting': 1, 'flying': 1, 'poison': 1, 'ground': 1, 'rock': 1, 'bug': 1, 'ghost': 2,
                   'steel': 1, 'fire': 1, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': 2, 'ice': 1, 'dragon': 1,
                   'dark': 2, 'fairy': 1},
        'steel': {'normal': 1, 'fighting': 1, 'flying': 1, 'poison': 1, 'ground': 1, 'rock': 2, 'bug': 1, 'ghost': 1,
                  'steel': .5, 'fire': .5, 'water': .5, 'grass': 1, 'electric': .5, 'psychic': 1, 'ice': 2, 'dragon': 1,
                  'dark': 1, 'fairy': 2},
        'fire': {'normal': 1, 'fighting': 1, 'flying': 1, 'poison': 1, 'ground': 1, 'rock': .5, 'bug': 2, 'ghost': 1,
                   'steel': 2, 'fire': .5, 'water': .5, 'grass': 2, 'electric': 1, 'psychic': 1, 'ice': 2, 'dragon': .5,
                   'dark': 1, 'fairy': 1},
        'water': {'normal': 1, 'fighting': 1, 'flying': 1, 'poison': 1, 'ground': 2, 'rock': 2, 'bug': 1, 'ghost': 1,
                   'steel': 1, 'fire': 2, 'water': .5, 'grass': .5, 'electric': 1, 'psychic': 1, 'ice': 1, 'dragon': .5,
                   'dark': 1, 'fairy': 1},
        'grass': {'normal': 1, 'fighting': 1, 'flying': .5, 'poison': .5, 'ground': 2, 'rock': 2, 'bug': .5, 'ghost': 1,
                   'steel': .5, 'fire': .5, 'water': 2, 'grass': .5, 'electric': 1, 'psychic': 1, 'ice': 1, 'dragon': .5,
                   'dark': 1, 'fairy': 1},
        'electric': {'normal': 1, 'fighting': 1, 'flying': 2, 'poison': 1, 'ground': 0, 'rock': 1, 'bug': 1, 'ghost': 1,
                   'steel': 1, 'fire': 1, 'water': 2, 'grass': .5, 'electric': .5, 'psychic': 1, 'ice': 1, 'dragon': .5,
                   'dark': 1, 'fairy': 1},
        'psychic': {'normal': 1, 'fighting': 2, 'flying': 1, 'poison': 2, 'ground': 1, 'rock': 1, 'bug': 1, 'ghost': 1,
                   'steel': .5, 'fire': 1, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': .5, 'ice': 1, 'dragon': 1,
                   'dark': 0, 'fairy': 1},
        'ice': {'normal': 1, 'fighting': 1, 'flying': 2, 'poison': 1, 'ground': 2, 'rock': 1, 'bug': 1, 'ghost': 1,
                   'steel': .5, 'fire': .5, 'water': .5, 'grass': 2, 'electric': 1, 'psychic': 1, 'ice': .5, 'dragon': 2,
                   'dark': 1, 'fairy': 1},
        'dragon': {'normal': 1, 'fighting': 1, 'flying': 1, 'poison': 1, 'ground': 1, 'rock': 1, 'bug': 1, 'ghost': 1,
                   'steel': .5, 'fire': 1, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': 1, 'ice': 1, 'dragon': 2,
                   'dark': 1, 'fairy': 0},
        'dark': {'normal': 1, 'fighting': .5, 'flying': 1, 'poison': 1, 'ground': 1, 'rock': 1, 'bug': 1, 'ghost': 2,
                   'steel': 1, 'fire': 1, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': 2, 'ice': 1, 'dragon': 1,
                   'dark': .5, 'fairy': .5},
        'fairy': {'normal': 1, 'fighting': 2, 'flying': 1, 'poison': .5, 'ground': 1, 'rock': 1, 'bug': 1, 'ghost': 1,
                    'steel': .5, 'fire': .5, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': 1, 'ice': 1, 'dragon': 2,
                    'dark': 2, 'fairy': 1},
        'freeze-dry': {'normal': 1, 'fighting': 1, 'flying': 2, 'poison': 1, 'ground': 2, 'rock': 1, 'bug': 1, 'ghost': 1,
                        'steel': .5, 'fire': .5, 'water': 2, 'grass': 2, 'electric': 1, 'psychic': 1, 'ice': .5, 'dragon': 2,
                        'dark': 1, 'fairy': 1},
    }
    # Damage = ((((2 * level/ 5) + 2) * Power * attackStat/defenseStat)/50) * Weather * Critical * STAB * TypeEffectiveness * Random * Burn * other
    # Damage is always at least 1

    if attack.name == 'seismic-toss' or attack.name == 'night-shade':
        return attacker.level
    elif attack.name == 'super-fang':
        return defender.effectiveStats['HP'] * (defender.hp / 100)
    elif attack.name in ['counter', 'mirror-coat']:
        if not defender.hasMoved:
            return 0
        return attacker.lastDamageTaken * 2

    if attack.name == 'pyro-ball':
        attack.type = attack.type[0]

    # Items that block damage
    if 'Air Balloon' in defender.item and attack.type.name == 'ground':
        return 0

    # Abilities that block or absorb damage
    if 'Levitate' in defender.ability and attack.type.name == 'ground':
        return 0
    elif 'Flash Fire' in defender.ability and attack.type.name == 'fire':
        return 0
    elif 'Water Absorb' in defender.ability and attack.type.name == 'water':
        defender.heal(defender.leveledStats['HP'] * .25)
        return 0
    elif 'Volt Absorb' in defender.ability and attack.type.name == 'electric':
        defender.heal(defender.leveledStats['HP'] * .25)
        return 0
    elif 'Dry Skin' in defender.ability and attack.type.name == 'water':
        defender.heal(defender.leveledStats['HP'] * .25)
        return 0
    elif 'Storm Drain' in defender.ability and attack.type.name == 'water':
        defender.boost_stat('Spa', 1)
        return 0
    elif 'Sap Sipper' in defender.ability and attack.type.name == 'grass':
        defender.boost_stat('Atk', 1)
        return 0
    elif 'Motor Drive' in defender.ability and attack.type.name == 'electric':
        defender.boost_stat('Spe', 1)
        return 0
    elif 'Lightning Rod' in defender.ability and attack.type.name == 'electric':
        defender.boost_stat('Spa', 1)
        return 0

    # Battle Armor and Shell Armor ignores crits
    if 'Battle Armor' in defender.ability or 'Shell Armor' in defender.ability:
        isCrit = False

    # Determine formula variables
    level = attacker.level

    other = 1
    # Dynamic power move exceptions
    if attack.name == 'gyro-ball':
        power = 25 * (defender.effectiveStats['Spe'] / attacker.effectiveStats['Spe'])
    elif attack.name == 'heavy-slam' or attack.name == 'heat-crash':
        weightPowerTable = {
            'minWeight': [.33, .25, .2, 0],
            'maxWeight': [.5, .33, .25, .2],
            'power': [60, 80, 100, 120]
        }
        weightPercentage = defender.weight / attacker.weight
        if weightPercentage > .5:
            power = 40
        else:
            for i in range(4):
                if weightPowerTable['minWeight'][i] <= weightPercentage < weightPowerTable['maxWeight'][i]:
                    power = weightPowerTable['power'][i]
                    break
    elif attack.name == 'grass-knot' or attack.name == 'low-kick':
        weightPowerTable = {    # weights are in kg, api request is hectograms
            'lowerWeight': [0, 10, 25, 50, 100, 200],
            'upperWeight': [10, 25, 50, 100, 200, 99999],
            'power': [20, 40, 60, 80, 100, 120]
        }
        for i in range(6):
            if weightPowerTable['lowerWeight'][i] <= defender.weight / 10 < weightPowerTable['upperWeight'][i]:
                power = weightPowerTable['power'][i]
                break
        if power is None:
            power = 120
    elif attack.name == 'facade':
        if attacker.statusCondition in ['BRN', 'PSN', 'PAR']:
            power = 140
        else:
            power = 70
    elif attack.name == 'stored-power':
        multiplier = 1
        for modifier in attacker.boosts:
            if attacker.boosts[modifier] > 0:
                multiplier += attacker.boosts[modifier]
        power = 20 * multiplier
    elif attack.name in ['dynamax-cannon', 'behemoth-blade', 'behemoth-bash']:
        if defender.isDynamaxed:
            other *= 2
        power = 100
    elif attack.name == 'triple-axel':
        power = 40
    elif attack.name == 'techno-blast':
        if attacker.item == 'Douse Drive':
            attack.type.name = 'water'
            power = 120
    elif attack.name == 'hex':
        if defender.statusCondition is not None:
            power = 130
        else:
            power = 65
    elif attack.name == 'acrobatics':
        if not attacker.item:
            power = 110
        else:
            power = 55
    elif attack.name == 'payback':
        if defender.hasMoved:
            power = 100
        else:
            power = 50
    else:
        power = attack.power

    if attack.damage_class.name == 'physical':
        if attack.name == 'body-press':
            attackStat = attacker.effectiveStats['Def']
            defenseStat = defender.effectiveStats['Def']
        elif attack.name == 'foul-play':
            attackStat = defender.effectiveStats['Atk']
            defenseStat = defender.effectiveStats['Def']
        else:
            attackStat = attacker.effectiveStats['Atk']
            defenseStat = defender.effectiveStats['Def']
        if isCrit:
            defenseStat = defender.leveledStats['Def']
    elif attack.damage_class.name == 'special':
        if attack.name == 'psyshock':
            attackStat = attacker.effectiveStats['Spa']
            defenseStat = defender.effectiveStats['Def']
            if isCrit:
                defenseStat = defender.leveledStats['Def']
        else:
            attackStat = attacker.effectiveStats['Spa']
            defenseStat = defender.effectiveStats['SpD']
            if isCrit:
                defenseStat = defender.leveledStats['SpD']
    try:
        if attack.type.name in attacker.type:
            if 'Adaptability' in attacker.ability:
                stab = 2
            else:
                stab = 1.5
        else:
            stab = 1
    except AttributeError:
        if attack.type[0] in attacker.type:
            if 'Adaptability' in attacker.ability:
                stab = 2
            else:
                stab = 1.5
        else:
            stab = 1

    # Calculate type effectiveness
    typeEffectiveness = 1
    # Freeze dry has a unique type effectiveness
    if attack.name == 'freeze-dry':
        for defenderType in defender.type:
            typeEffectiveness *= typeChart['freeze-dry'][defenderType]
    else:
        for defenderType in defender.type:
            typeEffectiveness *= typeChart[attack.type.name][defenderType]

    # This is the median damage roll
    randomDamage = 91

    # Factor in Burn damage reduction
    if attacker.statusCondition != 'BRN' or attack.damage_class.name != 'physical':
        burn = 1
    elif 'guts' in attacker.ability:
        burn = 1
    else:
        burn = .5

    # Weather effects
    weather = 1
    if battleState.weather['type'] is None:
        pass
    elif battleState.weather['type'] == 'Rain':
        if attack.type.name == 'water':
            weather = 1.5
        elif attack.type.name == 'fire':
            weather = .5
        elif attack.name == 'solar-beam' or attack.name == 'solar-blade':
            power *= .5
    elif battleState.weather['type'] == 'Sun':
        if attack.type.name == 'fire':
            weather = 1.5
        elif attack.type.name == 'water':
            weather = .5
    elif battleState.weather['type'] == 'Sandstorm' or battleState.weather['type'] == 'Hail':
        if attack.name == 'solar-beam' or attack.name == 'solar-blade':
            power *= .5

    if isCrit:
        if 'Sniper' in attacker.ability:
            critical = 2.25
        else:
            critical = 1.5
        if attack.damage_class.name == 'physical' and attacker.boosts['Atk'] < 0:
            attackStat = attacker.leveledStats['Atk']
        elif attack.damage_class.name == 'special' and attacker.boosts['Spa'] < 0:
            attackStat = attacker.leveledStats['Spa']
    else:
        critical = 1

    # Field conditions
    if defenderField['auroraVeil']['isUp']:
        other /= 2
    elif defenderField['reflect']['isUp'] and attack.damage_class.name == 'physical':
        other /= 2
    elif defenderField['lightScreen']['isUp'] and attack.damage_class.name == 'special':
        other /= 2

    # Items
    if 'Life Orb' in attacker.item and 'Choice Band' not in attacker.item and 'Choice Specs' not in attacker.item:
        other *= 1.3

    # If defender used protect
    if defender.isProtected:
        if not defender.isDynamaxed and attacker.isDynamaxed:
            other *= .25
        else:
            other = 0

    # Misc attacker abilities
    if 'Analytic' in attacker.ability and defender.hasMoved:
        other *= 1.3
    elif 'Torrent' in attacker.ability and attacker.hp < 33.4 and attack.type.name == 'water':
        attackStat *= 1.5
    elif 'Blaze' in attacker.ability and attacker.hp < 33.4 and attack.type.name == 'fire':
        attackStat *= 1.5
    elif 'Overgrow' in attacker.ability and attacker.hp < 33.4 and attack.type.name == 'grass':
        attackStat *= 1.5
    elif 'Swarm' in attacker.ability and attacker.hp < 33.4 and attack.type.name == 'bug':
        attackStat *= 1.5
    elif 'Sand Force' in attacker.ability and battleState.weather['type'] == 'Sandstorm' and attack.type.name in ['rock', 'ground', 'steel']:
        other *= 1.3
    elif 'Tinted Lens' in attacker.ability and typeEffectiveness < 1:
        typeEffectiveness *= 2
    elif 'Libero' in attacker.ability:
        attack.type = [attack.type.name]
        stab = 1.5
    elif 'Steelworker' in attacker.ability and attack.type.name == 'steel':
        attackStat *= 1.5
    elif 'Technician' in attacker.ability and attack.power <= 60:
        other *= 1.5
    elif 'Steely Spirit' in attacker.ability and attack.type.name == 'steel':
        other *= 1.5

    # Misc defender abilities
    if 'Ice Scales' in defender.ability and attack.damage_class.name == 'special':
        other *= .5
    elif 'Dry Skin' in defender.ability and attack.type.name == 'fire':
        other *= 1.25
    elif 'Thick Fat' in defender.ability and attack.type.name in ['fire', 'ice']:
        attackStat *= .5
    elif ('Filter' in defender.ability or 'Prism Armor' in defender.ability or 'Solid Rock' in defender.ability)\
            and typeEffectiveness > 1:
        other *= .75
    elif 'Wonder Guard' in defender.ability and typeEffectiveness <= 1:
        return 0

    damage = (((2 * level / 5) + 2) * power * attackStat/defenseStat/50) * weather * critical * stab * typeEffectiveness * (randomDamage / 100) * burn * other
    if damage < 1:
        damage = 1
    return damage


# Returns amount of damage caused by confusion self hit
def calculate_confusion_damage(pokemon):
    attackStat = pokemon.leveledStats['Atk']
    defenseStat = pokemon.leveledStats['Def']
    randomDamage = 92.5
    damage = (((2 * pokemon.level / 5) + 2) * 40 * attackStat / defenseStat / 50) * randomDamage
    if damage < 1:
        damage = 1
    return damage


# Returns pokemon from either team by using their name
def find_pokemon(battleState, name, isMyPokemon):
    if isMyPokemon:
        return battleState.myTeam[webInterface.get_pokemon_index(battleState.myTeam, name)]
    else:
        return battleState.opponentTeam[webInterface.get_pokemon_index(battleState.opponentTeam, name)]


def get_move(move_list, move_name):
    for move in move_list:
        if move.name == move_name:
            return move
    return None


# Returns the weighted average score of a list of outcomes
def get_average_score(outcome_list):
    average = 0
    for outcome in outcome_list:
        average += outcome.score * outcome.probability
    return average


# Sets the given outcome's score from the AI model
def calculate_score(outcome, prediction_function, scalar):
    myLead = outcome.battleState.myTeam[outcome.battleState.myLeadIndex]
    opponentLead = outcome.battleState.opponentTeam[outcome.battleState.opponentLeadIndex]
    battleState = outcome.battleState
    # Format the data
    dict = {
        'Elo': battleState.elo, 'P1AtkBoosts': myLead.boosts['Atk'], 'P1DefBoosts': myLead.boosts['Def'],
        'P1DynamaxAvailable': battleState.myDynamaxAvailable,
        'P1HasDamageEntryHazards': 'Stealth Rock' in battleState.myField['entryHazards'] or
                                   'Spikes' in battleState.myField['entryHazards'],
        'P1HasStickyWeb': 'Sticky Web' in battleState.myField['entryHazards'],
        'P1HasToxicSpikes': 'Toxic Spikes' in battleState.myField['entryHazards'],
        'P1LeadConfused': 'Confused' in myLead.volatileConditions,
        'P1LeadDynamaxed': myLead.isDynamaxed, 'P1LeadEncore': 'Encore' in myLead.volatileConditions,
        'P1LeadHP': myLead.hp, 'P1LeadLeechSeed': 'Leech Seed' in myLead.volatileConditions,
        'P1LeadStatus_BRN': myLead.statusCondition == 'BRN', 'P1LeadStatus_FALSE': myLead.statusCondition is None,
        'P1LeadStatus_FRZ': myLead.statusCondition == 'FRZ', 'P1LeadStatus_PAR': myLead.statusCondition == 'PAR',
        'P1LeadStatus_PSN': myLead.statusCondition == 'PAR', 'P1LeadStatus_SLP': myLead.statusCondition == 'SLP',
        'P1LeadStatus_TOX': myLead.statusCondition == 'TOX',
        'P1LeadTaunted': 'Taunt' in myLead.volatileConditions, 'P1LeadType1_Bug': False, 'P1LeadType1_Dark': False,
        'P1LeadType1_Dragon': False, 'P1LeadType1_Electric': False, 'P1LeadType1_Fairy': False,
        'P1LeadType1_Fighting': False, 'P1LeadType1_Fire': False, 'P1LeadType1_Flying': False,
        'P1LeadType1_Ghost': False, 'P1LeadType1_Grass': False, 'P1LeadType1_Ground': False,
        'P1LeadType1_Ice': False, 'P1LeadType1_Normal': False, 'P1LeadType1_Poison': False,
        'P1LeadType1_Psychic': False, 'P1LeadType1_Rock': False, 'P1LeadType1_Steel': False,
        'P1LeadType1_Water': False, 'P1LeadType2_Bug': False, 'P1LeadType2_Dark': False,
        'P1LeadType2_Dragon': False, 'P1LeadType2_Electric': False, 'P1LeadType2_Fairy': False,
        'P1LeadType2_Fighting': False, 'P1LeadType2_Fire': False, 'P1LeadType2_Flying': False,
        'P1LeadType2_Ghost': False, 'P1LeadType2_Grass': False, 'P1LeadType2_Ground': False,
        'P1LeadType2_Ice': False, 'P1LeadType2_None': False, 'P1LeadType2_Normal': False,
        'P1LeadType2_Poison': False, 'P1LeadType2_Psychic': False, 'P1LeadType2_Rock': False,
        'P1LeadType2_Steel': False, 'P1LeadType2_Water': False,
        'P1PokemonRemaining': battleState.get_my_pokemon_remaining(),
        'P1PokemonRevealed': battleState.get_my_pokemon_revealed(),
        'P1R1HP': None, 'P1R1Revealed': None, 'P1R2HP': None, 'P1R2Revealed': None, 'P1R3HP': None,
        'P1R3Revealed': None, 'P1R4HP': None, 'P1R4Revealed': None, 'P1R5HP': None, 'P1R5Revealed': None,
        'P1ScreenUp': battleState.myField['reflect']['isUp'] or battleState.myField['lightScreen']['isUp'] or
                      battleState.myField['auroraVeil']['isUp'],
        'P1SpaBoosts': myLead.boosts['Spa'], 'P1SpdBoosts': myLead.boosts['SpD'], 'P1SpeBoosts': myLead.boosts['Spe'],
        'P1TeamStatuses': battleState.get_my_team_statuses(), 'P2AtkBoosts': opponentLead.boosts['Atk'],
        'P2DefBoosts': opponentLead.boosts['Def'],
        'P2DynamaxAvailable': battleState.opponentDynamaxAvailable,
        'P2HasDamageEntryHazards': 'Stealth Rock' in battleState.opponentField['entryHazards'] or
                                   'Spikes' in battleState.opponentField['entryHazards'],
        'P2HasStickyWeb': 'Sticky Web' in battleState.opponentField['entryHazards'],
        'P2HasToxicSpikes': 'Toxic Spikes' in battleState.opponentField['entryHazards'],
        'P2LeadConfused': 'Confused' in opponentLead.volatileConditions,
        'P2LeadDynamaxed': opponentLead.isDynamaxed, 'P2LeadEncore': 'Encore' in opponentLead.volatileConditions,
        'P2LeadHP': opponentLead.hp, 'P2LeadLeechSeed': 'Leech Seed' in opponentLead.volatileConditions,
        'P2LeadStatus_BRN': opponentLead.statusCondition == 'BRN',
        'P2LeadStatus_FALSE': opponentLead.statusCondition is None,
        'P2LeadStatus_FRZ': opponentLead.statusCondition == 'FRZ',
        'P2LeadStatus_PAR': opponentLead.statusCondition == 'PAR',
        'P2LeadStatus_PSN': opponentLead.statusCondition == 'PSN',
        'P2LeadStatus_SLP': opponentLead.statusCondition == 'SLP',
        'P2LeadStatus_TOX': opponentLead.statusCondition == 'TOX',
        'P2LeadTaunted': 'Taunt' in opponentLead.volatileConditions,
        'P2LeadType1_Bug': False, 'P2LeadType1_Dark': False, 'P2LeadType1_Dragon': False, 'P2LeadType1_Electric': False,
        'P2LeadType1_Fairy': False, 'P2LeadType1_Fighting': False, 'P2LeadType1_Fire': False,
        'P2LeadType1_Flying': False, 'P2LeadType1_Ghost': False, 'P2LeadType1_Grass': False,
        'P2LeadType1_Ground': False, 'P2LeadType1_Ice': False, 'P2LeadType1_Normal': False,
        'P2LeadType1_Poison': False, 'P2LeadType1_Psychic': False, 'P2LeadType1_Rock': False,
        'P2LeadType1_Steel': False, 'P2LeadType1_Water': False, 'P2LeadType2_Bug': False,
        'P2LeadType2_Dark': False, 'P2LeadType2_Dragon': False, 'P2LeadType2_Electric': False,
        'P2LeadType2_Fairy': False, 'P2LeadType2_Fighting': False, 'P2LeadType2_Fire': False,
        'P2LeadType2_Flying': False, 'P2LeadType2_Ghost': False, 'P2LeadType2_Grass': False,
        'P2LeadType2_Ground': False, 'P2LeadType2_Ice': False, 'P2LeadType2_None': False, 'P2LeadType2_Normal': False,
        'P2LeadType2_Poison': False, 'P2LeadType2_Psychic': False, 'P2LeadType2_Rock': False,
        'P2LeadType2_Steel': False, 'P2LeadType2_Water': False,
        'P2PokemonRemaining': battleState.get_opponent_pokemon_remaining(),
        'P2PokemonRevealed': battleState.get_opponent_pokemon_revealed(),
        'P2R1HP': None, 'P2R1Revealed': None, 'P2R2HP': None, 'P2R2Revealed': None, 'P2R3HP': None,
        'P2R3Revealed': None, 'P2R4HP': None, 'P2R4Revealed': None, 'P2R5HP': None, 'P2R5Revealed': None,
        'P2ScreenUp': battleState.opponentField['reflect']['isUp'] or battleState.opponentField['lightScreen']['isUp'] or
                      battleState.opponentField['auroraVeil']['isUp'],
        'P2SpaBoosts': opponentLead.boosts['Spa'], 'P2SpdBoosts': opponentLead.boosts['SpD'],
        'P2SpeBoosts': opponentLead.boosts['Spe'], 'P2TeamStatuses': battleState.get_opponent_team_statuses(),
        'Terrain_Electric Terrain': 'Electric Terrain' == battleState.terrain['type'],
        'Terrain_Grassy Terrain': 'Grassy Terrain' == battleState.terrain['type'],
        'Terrain_Misty Terrain': 'Misty Terrain' == battleState.terrain['type'],
        'Terrain_None': battleState.terrain['type'] is None,
        'Terrain_Psychic Terrain': 'Psychic Terrain' == battleState.terrain['type'],
        'Weather_Hail': 'Hail' == battleState.weather['type'],
        'Weather_None': battleState.weather['type'] is None,
        'Weather_Rain': 'Rain' == battleState.weather['type'],
        'Weather_Sandstorm': 'Sandstorm' == battleState.weather['type'],
        'Weather_Sun': 'Sun' == battleState.weather['type']
    }
    # Fill in lead's types
    type_dict = {
        'bug': ('P1LeadType1_Bug', 'P1LeadType2_Bug', 'P2LeadType1_Bug', 'P2LeadType2_Bug'),
        'dark': ('P1LeadType1_Dark', 'P1LeadType2_Dark', 'P2LeadType1_Dark', 'P2LeadType2_Dark'),
        'dragon': ('P1LeadType1_Dragon', 'P1LeadType2_Dragon', 'P2LeadType1_Dragon', 'P2LeadType2_Dragon'),
        'electric': ('P1LeadType1_Electric', 'P1LeadType2_Electric', 'P2LeadType1_Electric', 'P2LeadType2_Electric'),
        'fairy': ('P1LeadType1_Fairy', 'P1LeadType2_Fairy', 'P2LeadType1_Fairy', 'P2LeadType2_Fairy'),
        'fighting': ('P1LeadType1_Fighting', 'P1LeadType2_Fighting', 'P2LeadType1_Fighting', 'P2LeadType2_Fighting'),
        'fire': ('P1LeadType1_Fire', 'P1LeadType2_Fire', 'P2LeadType1_Fire', 'P2LeadType2_Fire'),
        'flying': ('P1LeadType1_Flying', 'P1LeadType2_Flying', 'P2LeadType1_Flying', 'P2LeadType2_Flying'),
        'ghost': ('P1LeadType1_Ghost', 'P1LeadType2_Ghost', 'P2LeadType1_Ghost', 'P2LeadType2_Ghost'),
        'grass': ('P1LeadType1_Grass', 'P1LeadType2_Grass', 'P2LeadType1_Grass', 'P2LeadType2_Grass'),
        'ground': ('P1LeadType1_Ground', 'P1LeadType2_Ground', 'P2LeadType1_Ground', 'P2LeadType1_Ground'),
        'ice': ('P1LeadType1_Ice', 'P1LeadType2_Ice', 'P2LeadType1_Ice', 'P2LeadType2_Ice'),
        'normal': ('P1LeadType1_Normal', 'P1LeadType2_Normal', 'P2LeadType1_Normal', 'P2LeadType2_Normal'),
        'poison': ('P1LeadType1_Poison', 'P1LeadType2_Poison', 'P2LeadType1_Poison', 'P2LeadType2_Poison'),
        'psychic': ('P1LeadType1_Psychic', 'P1LeadType2_Psychic', 'P2LeadType1_Psychic', 'P2LeadType2_Psychic'),
        'rock': ('P1LeadType1_Rock', 'P1LeadType2_Rock', 'P2LeadType1_Rock', 'P2LeadType2_Rock'),
        'steel': ('P1LeadType1_Steel', 'P1LeadType2_Steel', 'P2LeadType1_Steel', 'P2LeadType2_Steel'),
        'water': ('P1LeadType1_Water', 'P1LeadType2_Water', 'P2LeadType1_Water', 'P2LeadType2_Water')
    }

    # Fill in both leads' types
    dict[type_dict[myLead.type[0]][0]] = True
    if len(myLead.type) > 1:
        dict[type_dict[myLead.type[1]][1]] = True
    dict[type_dict[opponentLead.type[0]][2]] = True
    if len(opponentLead.type) > 1:
        dict[type_dict[opponentLead.type[1]][3]] = True

    # Fill in reserve information
    reserveIndex = 0
    reserveHealth = ['P1R1HP', 'P1R2HP', 'P1R3HP', 'P1R4HP', 'P1R5HP']
    reserveRevealed = ['P1R1Revealed', 'P1R2Revealed', 'P1R3Revealed', 'P1R4Revealed', 'P1R5Revealed']
    for member in battleState.myTeam:
        if member is battleState.myTeam[battleState.myLeadIndex]:
            continue
        dict[reserveHealth[reserveIndex]] = member.hp
        dict[reserveRevealed[reserveIndex]] = member.isRevealed
        reserveIndex += 1
    reserveIndex = 0
    reserveHealth = ['P2R1HP', 'P2R2HP', 'P2R3HP', 'P2R4HP', 'P2R5HP']
    reserveRevealed = ['P2R1Revealed', 'P2R2Revealed', 'P2R3Revealed', 'P2R4Revealed', 'P2R5Revealed']
    for member in battleState.opponentTeam:
        if member is battleState.opponentTeam[battleState.opponentLeadIndex]:
            continue
        dict[reserveHealth[reserveIndex]] = member.hp
        dict[reserveRevealed[reserveIndex]] = True
        reserveIndex += 1
    # Fill in information for unrevealed opponent team members
    while reserveIndex < 5:
        dict[reserveHealth[reserveIndex]] = 100
        dict[reserveRevealed[reserveIndex]] = False
        reserveIndex += 1

    #df = pd.DataFrame.from_dict(dict)
    df = pd.DataFrame(dict, index=[0])
    numerical_columns = ['Elo', 'P1AtkBoosts', 'P1DefBoosts', 'P1LeadHP', 'P1PokemonRemaining', 'P1PokemonRevealed',
                         'P1R1HP', 'P1R2HP', 'P1R3HP', 'P1R4HP', 'P1R5HP', 'P1SpaBoosts', 'P1SpdBoosts', 'P1SpeBoosts',
                         'P1TeamStatuses', 'P2AtkBoosts', 'P2DefBoosts', 'P2LeadHP', 'P2PokemonRemaining',
                         'P2PokemonRevealed', 'P2R1HP', 'P2R2HP', 'P2R3HP', 'P2R4HP', 'P2R5HP', 'P2SpaBoosts',
                         'P2SpdBoosts', 'P2SpeBoosts', 'P2TeamStatuses']
    # Change boolean columns to 1s and 0s
    for column in df.columns:
        if column not in numerical_columns:
            logging.debug('Converting column: ' + str(column))
            df[column] = df[column].astype(int)

    df = df.sort_index(axis=1)
    arr = df.to_numpy()
    #min_max_scaler = MinMaxScaler()
    #arr = min_max_scaler.fit_transform(arr)
    arr = scalar.transform(arr)
    arr = np.asarray(arr.astype('float32'))
    prediction = prediction_function(arr.reshape(1, -1))
    outcome.set_score(prediction[0][-1])


# Takes a list of outcomes. Returns the outcome with the lowest score
def get_worst_case(outcome_list):
    worst_outcome = outcome_list[0]
    for outcome in outcome_list:
        if outcome.score < worst_outcome.score:
            worst_outcome = outcome
    return worst_outcome


# Takes a list of outcomes and returns the outcome with the highest score
def get_best_case(outcome_list):
    best_outcome = outcome_list[0]
    for outcome in outcome_list:
        if outcome.score > best_outcome.score:
            best_outcome = outcome
    return best_outcome


def get_worst_outcome(outcome_list):
    worst_score = 99
    worst_outcome = outcome_list[0]
    for outcome in outcome_list:
        children_list = outcome.get_children()
        score = get_average_score(children_list)
        if score < worst_score:
            worst_score = score
            worst_outcome = outcome
    return worst_outcome


# Best outcome at index 0, worst outcome at index -1
def sort_best_outcomes(outcome_list):
    # Assign scores to each outcome in the given list based on their children's scores
    for outcome in outcome_list:
        children_list = outcome.get_children()
        score = get_average_score(children_list)
        outcome.set_score(score)
    # Sort the list of outcomes based on their scores
    for i in range(len(outcome_list)):
        max_index = i
        for k in range(i + 1, len(outcome_list)):
            if outcome_list[max_index].score < outcome_list[k].score:
                max_index = k
        # Swap largest element to current index of list
        outcome_list[i], outcome_list[max_index] = outcome_list[max_index], outcome_list[i]


# Returns list of moves to consider on a given turn
def attacks_to_consider(outcome, move_list, attacker, defender):
    typeChart = {
        'normal': {'normal': 1, 'fighting': 1, 'flying': 1, 'poison': 1, 'ground': 1, 'rock': .5, 'bug': 1, 'ghost': 0,
                   'steel': .5, 'fire': 1, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': 1, 'ice': 1, 'dragon': 1,
                   'dark': 1, 'fairy': 1},
        'fighting': {'normal': 2, 'fighting': 1, 'flying': .5, 'poison': .5, 'ground': 1, 'rock': 2, 'bug': .5,
                     'ghost': 0,
                     'steel': 2, 'fire': 1, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': .5, 'ice': 2, 'dragon': 1,
                     'dark': 2, 'fairy': .5},
        'flying': {'normal': 1, 'fighting': 2, 'flying': 1, 'poison': 1, 'ground': 1, 'rock': .5, 'bug': 2, 'ghost': 1,
                   'steel': .5, 'fire': 1, 'water': 1, 'grass': 2, 'electric': .5, 'psychic': 1, 'ice': 1, 'dragon': 1,
                   'dark': 1, 'fairy': 1},
        'poison': {'normal': 1, 'fighting': 1, 'flying': 1, 'poison': .5, 'ground': .5, 'rock': .5, 'bug': 1,
                   'ghost': .5,
                   'steel': 0, 'fire': 1, 'water': 1, 'grass': 2, 'electric': 1, 'psychic': 1, 'ice': 1, 'dragon': 1,
                   'dark': 1, 'fairy': 2},
        'ground': {'normal': 1, 'fighting': 1, 'flying': 0, 'poison': 2, 'ground': 1, 'rock': 2, 'bug': .5, 'ghost': 1,
                   'steel': 2, 'fire': 2, 'water': 1, 'grass': .5, 'electric': 2, 'psychic': 1, 'ice': 1, 'dragon': 1,
                   'dark': 1, 'fairy': 1},
        'rock': {'normal': 1, 'fighting': .5, 'flying': 2, 'poison': 1, 'ground': .5, 'rock': .5, 'bug': 2, 'ghost': 1,
                 'steel': .5, 'fire': 2, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': 1, 'ice': 2, 'dragon': 1,
                 'dark': 1, 'fairy': 1},
        'bug': {'normal': 1, 'fighting': .5, 'flying': .5, 'poison': .5, 'ground': 1, 'rock': 1, 'bug': 1, 'ghost': .5,
                'steel': .5, 'fire': .5, 'water': 1, 'grass': 2, 'electric': 1, 'psychic': 2, 'ice': 1, 'dragon': 1,
                'dark': 2, 'fairy': .5},
        'ghost': {'normal': 0, 'fighting': 1, 'flying': 1, 'poison': 1, 'ground': 1, 'rock': 1, 'bug': 1, 'ghost': 2,
                  'steel': 1, 'fire': 1, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': 2, 'ice': 1, 'dragon': 1,
                  'dark': 2, 'fairy': 1},
        'steel': {'normal': 1, 'fighting': 1, 'flying': 1, 'poison': 1, 'ground': 1, 'rock': 2, 'bug': 1, 'ghost': 1,
                  'steel': .5, 'fire': .5, 'water': .5, 'grass': 1, 'electric': .5, 'psychic': 1, 'ice': 2, 'dragon': 1,
                  'dark': 1, 'fairy': 2},
        'fire': {'normal': 1, 'fighting': 1, 'flying': 1, 'poison': 1, 'ground': 1, 'rock': .5, 'bug': 2, 'ghost': 1,
                 'steel': 2, 'fire': .5, 'water': .5, 'grass': 2, 'electric': 1, 'psychic': 1, 'ice': 2, 'dragon': .5,
                 'dark': 1, 'fairy': 1},
        'water': {'normal': 1, 'fighting': 1, 'flying': 1, 'poison': 1, 'ground': 2, 'rock': 2, 'bug': 1, 'ghost': 1,
                  'steel': 1, 'fire': 2, 'water': .5, 'grass': .5, 'electric': 1, 'psychic': 1, 'ice': 1, 'dragon': .5,
                  'dark': 1, 'fairy': 1},
        'grass': {'normal': 1, 'fighting': 1, 'flying': .5, 'poison': .5, 'ground': 2, 'rock': 2, 'bug': .5, 'ghost': 1,
                  'steel': .5, 'fire': .5, 'water': 2, 'grass': .5, 'electric': 1, 'psychic': 1, 'ice': 1, 'dragon': .5,
                  'dark': 1, 'fairy': 1},
        'electric': {'normal': 1, 'fighting': 1, 'flying': 2, 'poison': 1, 'ground': 0, 'rock': 1, 'bug': 1, 'ghost': 1,
                     'steel': 1, 'fire': 1, 'water': 2, 'grass': .5, 'electric': .5, 'psychic': 1, 'ice': 1,
                     'dragon': .5,
                     'dark': 1, 'fairy': 1},
        'psychic': {'normal': 1, 'fighting': 2, 'flying': 1, 'poison': 2, 'ground': 1, 'rock': 1, 'bug': 1, 'ghost': 1,
                    'steel': .5, 'fire': 1, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': .5, 'ice': 1, 'dragon': 1,
                    'dark': 0, 'fairy': 1},
        'ice': {'normal': 1, 'fighting': 1, 'flying': 2, 'poison': 1, 'ground': 2, 'rock': 1, 'bug': 1, 'ghost': 1,
                'steel': .5, 'fire': .5, 'water': .5, 'grass': 2, 'electric': 1, 'psychic': 1, 'ice': .5, 'dragon': 2,
                'dark': 1, 'fairy': 1},
        'dragon': {'normal': 1, 'fighting': 1, 'flying': 1, 'poison': 1, 'ground': 1, 'rock': 1, 'bug': 1, 'ghost': 1,
                   'steel': .5, 'fire': 1, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': 1, 'ice': 1, 'dragon': 2,
                   'dark': 1, 'fairy': 0},
        'dark': {'normal': 1, 'fighting': .5, 'flying': 1, 'poison': 1, 'ground': 1, 'rock': 1, 'bug': 1, 'ghost': 2,
                 'steel': 1, 'fire': 1, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': 2, 'ice': 1, 'dragon': 1,
                 'dark': .5, 'fairy': .5},
        'fairy': {'normal': 1, 'fighting': 2, 'flying': 1, 'poison': .5, 'ground': 1, 'rock': 1, 'bug': 1, 'ghost': 1,
                  'steel': .5, 'fire': .5, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': 1, 'ice': 1, 'dragon': 2,
                  'dark': 2, 'fairy': 1},
        'freeze-dry': {'normal': 1, 'fighting': 1, 'flying': 2, 'poison': 1, 'ground': 2, 'rock': 1, 'bug': 1,
                       'ghost': 1,
                       'steel': .5, 'fire': .5, 'water': 2, 'grass': 2, 'electric': 1, 'psychic': 1, 'ice': .5,
                       'dragon': 2,
                       'dark': 1, 'fairy': 1},
    }
    high_priority_moves = []
    standard_priority_moves = []
    low_priority_moves = []
    status_moves = []
    weather = outcome.battleState.weather['type']

    for move in move_list:
        if move.damage_class.name == 'status' or move.meta.ailment_chance >= 30:
            if move.name in ['protect, detect, max-guard'] and attacker.lastUsedMove in ['protect, detect, max-guard']:
                low_priority_moves.append(move)
            else:
                status_moves.append(move)
            continue
        type_effectiveness = 1
        for defender_type in defender.type:
            if move_in_list(move, status_moves):
                continue
            if move.name == 'freeze-dry':
                type_effectiveness *= typeChart['freeze-dry'][defender_type]
            else:
                type_effectiveness *= typeChart[move.type.name][defender_type]
        if 'Levitate' in defender.ability and move.type.name == 'ground':
            type_effectiveness = 0
        elif 'Flash Fire' in defender.ability and move.type.name == 'fire':
            type_effectiveness = 0
        elif 'Water Absorb' in defender.ability and move.type.name == 'water':
            type_effectiveness = 0
        elif 'Volt Absorb' in defender.ability and move.type.name == 'electric':
            type_effectiveness = 0
        elif 'Dry Skin' in defender.ability and move.type.name == 'water':
            type_effectiveness = 0
        elif 'Storm Drain' in defender.ability and move.type.name == 'water':
            type_effectiveness = 0
        elif 'Sap Sipper' in defender.ability and move.type.name == 'grass':
            type_effectiveness = 0
        elif 'Motor Drive' in defender.ability and move.type.name == 'electric':
            type_effectiveness = 0
        elif 'Lightning Rod' in defender.ability and move.type.name == 'electric':
            type_effectiveness = 0

        if type_effectiveness > 1 or (type_effectiveness > .5 and move.type.name == 'fire' and weather == 'Sun')\
                or (type_effectiveness > .5 and move.type.name == 'water' and weather == 'Rain'):
            high_priority_moves.append(move)
        elif type_effectiveness == 1 and move.type.name in attacker.type:
            high_priority_moves.append(move)
        elif type_effectiveness == 1 or (type_effectiveness > .25 and move.type.name == 'fire' and weather == 'Sun')\
                or (type_effectiveness > .25 and move.type.name == 'water' and weather == 'Rain'):
            standard_priority_moves.append(move)
        else:
            low_priority_moves.append(move)

    if high_priority_moves:
        high_priority_moves += status_moves
        return high_priority_moves
    elif standard_priority_moves:
        standard_priority_moves += status_moves
        return standard_priority_moves
    else:
        low_priority_moves += status_moves
        return low_priority_moves


def move_in_list(move, move_list):
    for move2 in move_list:
        if id(move) == id(move2):
            return True
    return False


# Returns list of switch options
def switches_to_consider(team, opposing_lead, opposing_move_list):
    typeChart = {
        'normal': {'normal': 1, 'fighting': 1, 'flying': 1, 'poison': 1, 'ground': 1, 'rock': .5, 'bug': 1, 'ghost': 0,
                   'steel': .5, 'fire': 1, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': 1, 'ice': 1, 'dragon': 1,
                   'dark': 1, 'fairy': 1},
        'fighting': {'normal': 2, 'fighting': 1, 'flying': .5, 'poison': .5, 'ground': 1, 'rock': 2, 'bug': .5,
                     'ghost': 0,
                     'steel': 2, 'fire': 1, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': .5, 'ice': 2, 'dragon': 1,
                     'dark': 2, 'fairy': .5},
        'flying': {'normal': 1, 'fighting': 2, 'flying': 1, 'poison': 1, 'ground': 1, 'rock': .5, 'bug': 2, 'ghost': 1,
                   'steel': .5, 'fire': 1, 'water': 1, 'grass': 2, 'electric': .5, 'psychic': 1, 'ice': 1, 'dragon': 1,
                   'dark': 1, 'fairy': 1},
        'poison': {'normal': 1, 'fighting': 1, 'flying': 1, 'poison': .5, 'ground': .5, 'rock': .5, 'bug': 1,
                   'ghost': .5,
                   'steel': 0, 'fire': 1, 'water': 1, 'grass': 2, 'electric': 1, 'psychic': 1, 'ice': 1, 'dragon': 1,
                   'dark': 1, 'fairy': 2},
        'ground': {'normal': 1, 'fighting': 1, 'flying': 0, 'poison': 2, 'ground': 1, 'rock': 2, 'bug': .5, 'ghost': 1,
                   'steel': 2, 'fire': 2, 'water': 1, 'grass': .5, 'electric': 2, 'psychic': 1, 'ice': 1, 'dragon': 1,
                   'dark': 1, 'fairy': 1},
        'rock': {'normal': 1, 'fighting': .5, 'flying': 2, 'poison': 1, 'ground': .5, 'rock': .5, 'bug': 2, 'ghost': 1,
                 'steel': .5, 'fire': 2, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': 1, 'ice': 2, 'dragon': 1,
                 'dark': 1, 'fairy': 1},
        'bug': {'normal': 1, 'fighting': .5, 'flying': .5, 'poison': .5, 'ground': 1, 'rock': 1, 'bug': 1, 'ghost': .5,
                'steel': .5, 'fire': .5, 'water': 1, 'grass': 2, 'electric': 1, 'psychic': 2, 'ice': 1, 'dragon': 1,
                'dark': 2, 'fairy': .5},
        'ghost': {'normal': 0, 'fighting': 1, 'flying': 1, 'poison': 1, 'ground': 1, 'rock': 1, 'bug': 1, 'ghost': 2,
                  'steel': 1, 'fire': 1, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': 2, 'ice': 1, 'dragon': 1,
                  'dark': 2, 'fairy': 1},
        'steel': {'normal': 1, 'fighting': 1, 'flying': 1, 'poison': 1, 'ground': 1, 'rock': 2, 'bug': 1, 'ghost': 1,
                  'steel': .5, 'fire': .5, 'water': .5, 'grass': 1, 'electric': .5, 'psychic': 1, 'ice': 2, 'dragon': 1,
                  'dark': 1, 'fairy': 2},
        'fire': {'normal': 1, 'fighting': 1, 'flying': 1, 'poison': 1, 'ground': 1, 'rock': .5, 'bug': 2, 'ghost': 1,
                 'steel': 2, 'fire': .5, 'water': .5, 'grass': 2, 'electric': 1, 'psychic': 1, 'ice': 2, 'dragon': .5,
                 'dark': 1, 'fairy': 1},
        'water': {'normal': 1, 'fighting': 1, 'flying': 1, 'poison': 1, 'ground': 2, 'rock': 2, 'bug': 1, 'ghost': 1,
                  'steel': 1, 'fire': 2, 'water': .5, 'grass': .5, 'electric': 1, 'psychic': 1, 'ice': 1, 'dragon': .5,
                  'dark': 1, 'fairy': 1},
        'grass': {'normal': 1, 'fighting': 1, 'flying': .5, 'poison': .5, 'ground': 2, 'rock': 2, 'bug': .5, 'ghost': 1,
                  'steel': .5, 'fire': .5, 'water': 2, 'grass': .5, 'electric': 1, 'psychic': 1, 'ice': 1, 'dragon': .5,
                  'dark': 1, 'fairy': 1},
        'electric': {'normal': 1, 'fighting': 1, 'flying': 2, 'poison': 1, 'ground': 0, 'rock': 1, 'bug': 1, 'ghost': 1,
                     'steel': 1, 'fire': 1, 'water': 2, 'grass': .5, 'electric': .5, 'psychic': 1, 'ice': 1,
                     'dragon': .5,
                     'dark': 1, 'fairy': 1},
        'psychic': {'normal': 1, 'fighting': 2, 'flying': 1, 'poison': 2, 'ground': 1, 'rock': 1, 'bug': 1, 'ghost': 1,
                    'steel': .5, 'fire': 1, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': .5, 'ice': 1, 'dragon': 1,
                    'dark': 0, 'fairy': 1},
        'ice': {'normal': 1, 'fighting': 1, 'flying': 2, 'poison': 1, 'ground': 2, 'rock': 1, 'bug': 1, 'ghost': 1,
                'steel': .5, 'fire': .5, 'water': .5, 'grass': 2, 'electric': 1, 'psychic': 1, 'ice': .5, 'dragon': 2,
                'dark': 1, 'fairy': 1},
        'dragon': {'normal': 1, 'fighting': 1, 'flying': 1, 'poison': 1, 'ground': 1, 'rock': 1, 'bug': 1, 'ghost': 1,
                   'steel': .5, 'fire': 1, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': 1, 'ice': 1, 'dragon': 2,
                   'dark': 1, 'fairy': 0},
        'dark': {'normal': 1, 'fighting': .5, 'flying': 1, 'poison': 1, 'ground': 1, 'rock': 1, 'bug': 1, 'ghost': 2,
                 'steel': 1, 'fire': 1, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': 2, 'ice': 1, 'dragon': 1,
                 'dark': .5, 'fairy': .5},
        'fairy': {'normal': 1, 'fighting': 2, 'flying': 1, 'poison': .5, 'ground': 1, 'rock': 1, 'bug': 1, 'ghost': 1,
                  'steel': .5, 'fire': .5, 'water': 1, 'grass': 1, 'electric': 1, 'psychic': 1, 'ice': 1, 'dragon': 2,
                  'dark': 2, 'fairy': 1},
        'freeze-dry': {'normal': 1, 'fighting': 1, 'flying': 2, 'poison': 1, 'ground': 2, 'rock': 1, 'bug': 1,
                       'ghost': 1,
                       'steel': .5, 'fire': .5, 'water': 2, 'grass': 2, 'electric': 1, 'psychic': 1, 'ice': .5,
                       'dragon': 2,
                       'dark': 1, 'fairy': 1},
    }
    high_priority_switches = []
    standard_priority_switches = []
    low_priority_switches = []
    outspeed_switches = []
    for member in team:
        outspeeded = False
        try:
            if member.effectiveStats['Spe'] > opposing_lead.effectiveStats['Spe']:
                outspeeded = True
        except TypeError:
            try:
                if member.leveledStats['Spe'] > opposing_lead.effectiveStats['Spe']:
                    outspeeded = True
            except TypeError:
                pass
        if outspeeded:
            added = False
            for move in member.possibleMoves:
                type_effectiveness = 1
                for defender_type in opposing_lead.type:
                    type_effectiveness *= typeChart[move.type.name][defender_type]
                if type_effectiveness > 1:
                    high_priority_switches.append(member)
                    added = True
                    break
            if not added:
                outspeed_switches.append(member)
        resistances = 0
        weaknesses = 0
        for move in opposing_move_list:
            type_effectiveness = 1
            for defender_type in member.type:
                try:
                    type_effectiveness *= typeChart[move.type.name][defender_type]
                except AttributeError:
                    type_effectiveness *= typeChart[move.type[0].name][defender_type]
            if type_effectiveness < 1:
                resistances += 1
            elif type_effectiveness > 1:
                weaknesses += 1
        if weaknesses == 0 and resistances > 0:
            high_priority_switches.append(member)
        elif weaknesses == 0:
            standard_priority_switches.append(member)
        else:
            low_priority_switches.append(member)
    if high_priority_switches:
        return high_priority_switches
    elif standard_priority_switches:
        return standard_priority_switches + outspeed_switches
    elif outspeed_switches:
        return outspeed_switches
    else:
        return low_priority_switches


