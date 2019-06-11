# -*- coding: utf-8 -*-
# script of the Choice box v9
# @author Desktop Application team
# (c) 2014 Aldebaran Robotics

import os
import tempfile
import shutil
import uuid
import time
import random
import thread
import mutex
import xml.dom.minidom

class MyClass(GeneratedClass):
    def __init__(self):
        try: # disable autoBind
          GeneratedClass.__init__(self, False)
        except TypeError: # if NAOqi < 1.14
          GeneratedClass.__init__( self )

        # PROXIES INITIALIZATION
        self.animSpeech = ALProxy("ALAnimatedSpeech")
        self.tts = ALProxy("ALTextToSpeech")
        self.memory = ALProxy("ALMemory")
        self.motion = ALProxy("ALMotion")
        try:
            self.dialog = ALProxy("ALDialog")
            self.dcm = ALProxy( "DCM" )
        except:
            self.dialog = None
            self.dcm = None
            raise RuntimeError("Choice box cannot be launched, as Dialog and DCM are not available.")

        # VARIABLES INITIALIZATION
        self.aIdsTTS = []
        self.bSentencesInitialized = False
        self.bMustStop = False
        self.bIsRunning = False
        self.dialogIsRunning = False
        self.dialogIsLoaded = False
        self.bGoOut = False
        self.nCountNoReply = 0
        self.nCountFailure = 0
        self.bInConfirmation = False
        self.bVocabularyLoaded = False
        self.bInTactileSensorMenu = False
        self.bExternChoices = False
        self.rTimeLastChoiceSaid = -1.
        self.bIsSayingChoice = False
        self.nIndexChoice = 0
        self.sRecoInterruption = "" # = "wordRecognised" or "timeout" or "onStop" or "onTactileSensor"
        self.sPreviousAnswer = ""
        self.rTimeWhenActionMadeInTactileMenu = -1.
        self.langDict = {
            "Greek":"grg",
            "English":"enu",
            "French":"frf",
            "Japanese":"jpj",
            "Chinese":"mnc",
            "Korean":"kok",
            "German":"ged",
            "Italian":"iti",
            "Portuguese":"ptp",
            "Spanish":"spe",
            "Brazilian":"ptb",
            "Turkish":"trt",
            "Arabic":"arw",
            "Polish":"plp",
            "Czech":"czc",
            "Dutch":"dun",
            "Danish":"dad",
            "Finnish":"fif",
            "Swedish":"sws",
            "Russian":"rur",
            "Norwegian":"non",
            "CantoneseHongKong":"cah",
            "EnglishAustralia":"ena",
            "EnglishGB":"eng",
            "EnglishIndian":"eni",
            "FrenchCanadian":"frc",
            "MandarinTaiwan":"mnt",
            "SpanishMexico":"spm"
        }
        # variables used for the tactile sensor
        self.nFront = 0
        self.nMiddle = 0
        self.nRear = 0
        self.bSeqStarted = False
        self.bIsStoringParam = False
        self.bPressed = False
        self.mutexProcessCurrentState = mutex.mutex()
        self.mutexTactilTouched = mutex.mutex()
        self.mutexCheckIfSeqsCorrespondingLeft = mutex.mutex()
        # assuming that every sequence is after [0, 0, 0]
        # and then start with one tactil sensor activated
        # timeout must be either a number (int or float) not equal to 0 or an array of two numbers not equal to 0, a negative one and a positive one
        # a negative timeout means a minimum time that has to ellapse before the next step
        # a positive timeout means a maximum time before the next step must show up
        self.aSeqs = [{"name" : "Tap", "statesAndTimeout" : [ "1+", 0.35, "2+", 0.45, "0" ]},
                      {"name" : "TapFront", "statesAndTimeout" : [ "F", 1, "0" ]},
                      {"name" : "LongFront", "statesAndTimeout" : [ "F", -1, "F" ]},
                      {"name" : "TapMiddle", "statesAndTimeout" : [ "M", 1, "0" ]},
                      {"name" : "LongMiddle", "statesAndTimeout" : [ "M", -1, "M" ]},
                      {"name" : "TapRear", "statesAndTimeout" : [ "R", 1, "0" ]},
                      {"name" : "LongRear", "statesAndTimeout" : [ "R", -1, "R" ]},
                      {"name" : "CalmDown", "statesAndTimeout" : [ "1+", 0.5, "2+", -1, "2+" ]}]
        # sequences initialization
        aSeqsTemp = []
        for seq in self.aSeqs:
            try: # ensure that the sequence has at least a name and states and timeout defined
                seq["name"]
                seq["statesAndTimeout"]
                aSeqsTemp.append(seq)
            except:
                pass
        self.aSeqs = aSeqsTemp
        for seq in self.aSeqs:
            states = range( len( seq["statesAndTimeout"][0:len(seq["statesAndTimeout"]):2] ) )
            i = 0
            for state in seq["statesAndTimeout"][0:len(seq["statesAndTimeout"]):2]:
                states[i] = self.convertToArrayOfPossibleStates(state)
                i += 1
            seq["statesAndTimeout"][0:len(seq["statesAndTimeout"]):2] = states
        self.aDetectedSeqs = []
        self.aDetectedSeqs.extend(self.aSeqs)
        # end - variables used for the tactile sensor
        self.aChoices = []
        self.aDialogChoices = []
        self.aChoiceIndexes = []
        # parameters which can be changed from the parameters edition window
        self.sQuestion = ""
        self.nTimeoutReco = 10
        self.nTimeoutRecoConfirmation = 6
        self.nTimeoutTactile = 10
        self.nMaxCountNoReply = 3
        self.nMaxCountFailure = 5
        self.arUnderstoodThreshold = [0.0, 1.0] # range of self.rUnderstoodThreshold
        self.arConfirmationThreshold = [0.0, 1.0] # range of self.rConfirmationThreshold (must be higher than self.arUnderstoodThreshold)
        self.rUnderstoodThreshold = 0.2
        self.rConfirmationThreshold = 0.4
        self.bActivateHelpWhenFailure = True
        self.bRepeatValidatedChoice = True
        self.bActivateDefaultChoiceHelp = True
        self.bActivateDefaultChoiceRepeat = True
        self.bActivateDefaultChoiceExit = True
        self.BIND_PYTHON(self.getName(), "onTactilTouched")

# FUNCTIONS ===============================================================================================

    def onLoad(self):
        # initialize sentences for each language
        if( not self.bSentencesInitialized ):
            self.initializeSentences()
            self.bSentencesInitialized = True
        self.generateTopicFile()

# XML PARSER FOR SENTENCES INITIALIZATION
    def initializeSentences(self):
        "Initialize necessary sentences in each language."
        filename = self.behaviorAbsolutePath() + self.tryGetParameter( "Sentences file", "/Aldebaran/choice_sentences.xml" )
        if not self.fileExists(filename):
            raise RuntimeError("File " + filename + " could not be found. Please update your Choice box with a newer one from Choregraphe")
        try:
            doc = self.getFileContents( filename )
            dom = xml.dom.minidom.parseString( doc )
        except Exception as e:
            raise Exception( "The " + filename + " file is not in the right format. Check the special characters and that the syntax is correct.\n" + str(e) )
        try:
            tag = "sentences"
            mainBlock = dom.getElementsByTagName( tag )[0]
            tag = "translation"
            aTranslations = mainBlock.getElementsByTagName( tag )
            self.aAllWords = {}
            self.aAllSentences = {}
            for sTranslation in aTranslations:
                sLanguage = sTranslation.getAttribute("language")
                tag = "speechReco"
                blockSpeechReco = sTranslation.getElementsByTagName( tag )[0]
                # variable used for the speech recognition
                self.aAllWords[sLanguage] = {}
                aKinds = ["negative",
                          "positive",
                          "help",
                          "exit",
                          "repeat"]
                for sKind in aKinds:
                    tag = sKind
                    blockWordsForThisKind = blockSpeechReco.getElementsByTagName( sKind )[0]
                    self.aAllWords[sLanguage][sKind] = blockWordsForThisKind.getAttribute( "text" ).encode("utf-8").split("/")
                # end - variable used for the speech recognition
                tag = "tts"
                blockTTS = sTranslation.getElementsByTagName( tag )[0]
                # variable used for the Text-To-Speech
                self.aAllSentences[sLanguage] = {}
                aKinds = ["confirmation",
                          "enumMarks",
                          "helpEnumChoices",
                          "helpEnumDefault",
                          "helpTactile",
                          "notUnderstood",
                          "noQuestion",
                          "notUnderstoodAnims"]
                for sKind in aKinds:
                    tag = sKind
                    blockSentencesForThisKind = blockTTS.getElementsByTagName( sKind )[0]
                    self.aAllSentences[sLanguage][sKind] = blockSentencesForThisKind.getAttribute( "text" ).encode("utf-8").split("/")
                # end - variable used for the Text-To-Speech
        except Exception as e:
            raise Exception( "The " + filename + " file is not in the right format. Check that the '" + tag + "' tag is defined and with the right format.\n" + str(e) )

        # choices
        # !!! don't remove any comments from this variable !!!
        # (they are here to make the plugin work)
        self.aListAllChoices = {#Languages_TAG
                               }
        # end - choices

# INPUTS ACTIVATION PROCESSING ------------------------------------------------------------------------------
    def onInput_onStart(self, question=None):
        "Initialize variables and start box behaviour."
        self.logger.debug( "Input onStart stimulated." )
        if( self.bIsRunning): # to avoid starting the process twice
            return
        self.bIsRunning = True
        language = self.tts.getLanguage()
        try:
            self.aAllWords[language]
            self.aAllSentences[language]
        except:
            raise Exception( "The current language is not supported by this Choice box. It is probably deprecated. Try to use the one supplied in Choregraphe library instead." )
        self.asNegativeWords = self.aAllWords[language]["negative"]
        self.asPositiveWords = self.aAllWords[language]["positive"]
        self.asHelpWords = self.aAllWords[language]["help"]
        self.asExitWords = self.aAllWords[language]["exit"]
        self.asRepeatWords = self.aAllWords[language]["repeat"]
        self.bGoOut = False
        self.bVocabularyLoaded = False
        self.sRecoInterruption = ""
        self.sPreviousAnswer = ""
        self.bMustStop = False
        self.nCountNoReply = 0
        self.nCountFailure = 0
        self.bInConfirmation = False
        self.bInTactileSensorMenu = False
        self.bBrainAnimPaused = False
        self.bPressed = False
        self.rTimeWhenActionMadeInTactileMenu = -1.
        self.nFront = 0
        self.nMiddle = 0
        self.nRear = 0
        self.bSeqStarted = False
        self.guid = ""
        self.lastHeadPos = None
        self.rUnderstoodThreshold = self.tryGetParameter( "Minimum threshold to understand", 0.2 )
        self.rConfirmationThreshold = self.tryGetParameter( "Minimum threshold to be sure", 0.4 )
        self.nTimeoutReco = self.tryGetParameter( "Speech recognition timeout", 10 )
        self.nTimeoutRecoConfirmation = self.tryGetParameter( "Speech recognition timeout when confirmation", 6 )
        self.nTimeoutTactile = self.tryGetParameter( "Tactile sensor menu timeout", 10 )
        self.nMaxCountNoReply = self.tryGetParameter( "Maximum number of repetition when no reply", 3 )
        self.nMaxCountFailure = self.tryGetParameter( "Maximum number of repetition when failure", 5 )
        self.bActivateBrainLight =  True
        self.bActivateHelpWhenFailure = self.tryGetParameter( "Activate help when failure", True )
        self.bRepeatValidatedChoice = self.tryGetParameter( "Repeat validated choice", True )
        self.bActivateDefaultChoiceHelp = self.tryGetParameter( "Activate help command", True )
        self.bActivateDefaultChoiceRepeat = self.tryGetParameter( "Activate repeat command", True )
        self.bActivateDefaultChoiceExit = self.tryGetParameter( "Activate exit command", True )
        self.bodyLanguageMode = self.tryGetParameter( "Body language mode", "contextual" )
        self.dialog.setASRConfidenceThreshold(self.rUnderstoodThreshold )
        self.animSpeech.setBodyLanguageModeFromStr(self.bodyLanguageMode)
        self.aDefaultChoices = []
        self.aDialogDefaultChoices = []
        if (self.bActivateDefaultChoiceHelp):
            self.asHelpWords = self.removeUnauthorizedCharacters(self.asHelpWords)
            self.aDefaultChoices.append( self.asHelpWords )
            self.aDialogDefaultChoices += self.asHelpWords
        if (self.bActivateDefaultChoiceRepeat):
            self.asRepeatWords = self.removeUnauthorizedCharacters(self.asRepeatWords)
            self.aDefaultChoices.append( self.asRepeatWords )
            self.aDialogDefaultChoices += self.asRepeatWords
        if (self.bActivateDefaultChoiceExit):
            self.asExitWords = self.removeUnauthorizedCharacters(self.asExitWords)
            self.aDefaultChoices.append( self.asExitWords )
            self.aDialogDefaultChoices += self.asExitWords
        if( question == None ):
            question = ""
        if( len( self.aChoices ) > len( self.aDefaultChoices ) ): # if there is at least one choice (not a default one)
            self.nIndexChoice = len( self.aDefaultChoices )
        else: # if there are only default words
            self.nIndexChoice = 0
        self.bGoOut = False
        self.initQuestionAndChoices( question )
        # initialize tactile sensor handler
        self.initSeqDetected()
        # subscribe to tactile sensors extractors (launch tactile sensor handler)
        self.memory.subscribeToEvent( "FrontTactilTouched", self.getName(), "onTactilTouched" )
        self.memory.subscribeToEvent( "MiddleTactilTouched", self.getName(), "onTactilTouched" )
        self.memory.subscribeToEvent( "RearTactilTouched", self.getName(), "onTactilTouched" )
        if( not self.bGoOut ):
            self.questionRecognitionReaction()

    def onInput_choicesList(self, p):
        "Set choices list."
        self.logger.debug( "Input choicesList stimulated." )
        if( not self.bIsRunning ):
            self.bExternChoices = True
            language = self.tts.getLanguage()
            self.asNegativeWords = self.aAllWords[language]["negative"]
            self.asPositiveWords = self.aAllWords[language]["positive"]
            self.asHelpWords = self.aAllWords[language]["help"]
            self.asExitWords = self.aAllWords[language]["exit"]
            self.asRepeatWords = self.aAllWords[language]["repeat"]
            self.bActivateDefaultChoiceHelp = self.tryGetParameter( "Activate help command", True )
            self.bActivateDefaultChoiceRepeat = self.tryGetParameter( "Activate repeat command", True )
            self.bActivateDefaultChoiceExit = self.tryGetParameter( "Activate exit command", True )
            self.aDefaultChoices = []
            self.aDialogDefaultChoices = []
            if (self.bActivateDefaultChoiceHelp):
                self.aDefaultChoices.append( self.asHelpWords )
                self.aDialogDefaultChoices += self.asHelpWords
            if (self.bActivateDefaultChoiceRepeat):
                self.aDefaultChoices.append( self.asRepeatWords )
                self.aDialogDefaultChoices += self.asRepeatWords
            if (self.bActivateDefaultChoiceExit):
                self.aDefaultChoices.append( self.asExitWords )
                self.aDialogDefaultChoices += self.asExitWords
            self.aChoices = []
            self.aDialogChoices = []
            self.aChoiceIndexes = []
            self.aChoices.extend( self.aDefaultChoices )
            self.aDialogChoices += self.aDialogDefaultChoices
            index = 0
            for choice in p:
                if( self.isString(choice) ):
                    choice = choice.strip(" \t,;.\n") # remove space or tabs at beginning or end of a choice
                    if( choice != "" ):
                        choice = [ choice ]
                    else:
                        choice = []
                elif( self.isArray(choice) ):
                    if( choice != [] ):
                        for i in range( len( choice ) ):
                            if( self.isString(choice[i]) ):
                                choice[i] = choice[i].strip(" \t,;.\n") # remove space or tabs at beginning or end of a choice
                                if( len( choice[i] ) < 1 ):
                                    del choice[i]
                                    i -= 1 # to parse the good one next loop
                            else:
                                raise Exception( "Error in choices input syntax:\nIt must be an array of choices and each choice can be either a string or an array of strings (several possibilities for one choice)\nEx: ['choice1',['choice2a','choice2b']]\nbut: " + str(p) + " found" )
                else:
                    raise Exception( "Error in choices input syntax:\nIt must be an array of choices and each choice can be either a string or an array of strings (several possibilities for one choice)\nEx: ['choice1',['choice2a','choice2b']]\nbut: " + str(p) + " found" )
                if( len( choice ) > 0 ):
                    for sWord in choice:
                        for aDefaultChoice in self.aDefaultChoices:
                            if( sWord in aDefaultChoice ):
                                raise Exception( "Error in input choices list: You chose a word which is already used for default choices:\n" + str(sWord) + " is used for the default choice: " + str(aDefaultChoice[0]) )
                    self.aChoices.append( choice )
                    self.aDialogChoices += choice
                    self.aChoiceIndexes.append( index )
                index += 1
            self.dChoices = self.removeUnauthorizedCharacters(self.aDialogChoices)

    def onInput_onStop(self):
        "Stop box behaviour."
        self.logger.debug( "Input onStop stimulated." )
        if( self.bIsRunning ):
            self.goOut( self.asExitWords[0], "onStop" )
            self.sRecoInterruption = "onStop"
        else:
            self.onUnload()

# GENERAL FUNCTIONS ------------------------------------------------------------------------------------------

    def isString(self, strVariable):
        try:
            if( type( strVariable ) == type( "some string" ) ):
                return True
        except:
            pass
        return False

    def isArray(self, aVariable):
        try:
            if( type( aVariable ) == type( ["some array"] ) ):
                return True
        except:
            pass
        return False

    def fileExists(self, strPathFilename ):
        try:
            file = open( strPathFilename, 'r' )
            if( file ):
                file.close()
                return True
        except (IOError, os.error), err:
            pass
        return False

    def getFileContents(self, sFilename ):
        "read a file and return it's contents, or '' if not found, empty, ..."
        try:
            fileContent = open( sFilename )
            aBuf = fileContent.read()
            fileContent.close()
        except:
            try:
                fileContent.close()
            except:
                pass
            return ""
        return aBuf

    def getBrainLedName(self, nNumLed):
        "Get the name of the DCM led device from its number"
        "0 => front left; 1 => next in clock wise; until 11"
        numLed = nNumLed%12
        if( numLed <= 1 ):
            return "Head/Led/Front/Right/%d/Actuator/Value" % (1-numLed)
        elif( numLed >= 10 ):
            return "Head/Led/Front/Left/%d/Actuator/Value" % (numLed-10)
        elif( numLed <= 2 ):
            return "Head/Led/Middle/Right/%d/Actuator/Value" % (2-numLed)
        elif( numLed >= 9 ):
            return "Head/Led/Middle/Left/%d/Actuator/Value" % (numLed-9)
        elif( numLed <= 5 ):
            return "Head/Led/Rear/Right/%d/Actuator/Value" % (numLed-3)
        else:
            return "Head/Led/Rear/Left/%d/Actuator/Value" % (8-numLed)

    def skipTTS(self):
        for idtts in self.aIdsTTS:
            try:
                self.animSpeech.stop(idtts)
            except:
                try:
                    self.tts.stop(idtts)
                except:
                    self.logger.debug( "Warning: The Text-To-Speech could not have been stopped." )

    def removeIdTTS(self):
        for idTTS in self.aIdsTTS:
            try:
                self.aIdsTTS.remove( idTTS )
            except:
                self.logger.debug( "Warning: The task ID corresponding to the Text-To-Speech could not have been removed from the ID tasks list." )

    def tryGetParameter(self, sParameterName, defaultValue):
        try:
            return self.getParameter( sParameterName )
        except:
            return defaultValue

    def removeUnauthorizedCharacters(self, wordList):
        wordList = [x.replace("'","") for x in wordList]
        return wordList

    def getLanguage(self):
        try:
            language = self.langDict[self.tts.getLanguage()]
        except:
            raise RuntimeError("Language " + self.tts.getLanguage() + " is not available for Choice box!")
        return language

# QUESTION AND CHOICES INITIALIZATION ----------------------------------------------------------------------

    def initQuestionAndChoices(self, p):
        "Initialize the question and the choices."
        # question processing
        language = self.getLanguage()
        if( self.isString(p) ):
            self.sQuestion = p
        else:
            raise Exception( "Error in question input syntax:\nQuestion text\nexpected for example, but:\n" + str(p[0]) + "\nfound" )
        # choices processing
        if( not self.bExternChoices ):
            self.aChoices = []
            self.aDialogChoices = []
            self.aChoiceIndexes = []
            self.aChoices.extend( self.aDefaultChoices )
            self.aDialogChoices += self.aDialogDefaultChoices
            index = 0
            listChoices = self.aListAllChoices[self.tts.getLanguage()]
            for choice in listChoices:
                aChoice = choice.split( "/" )
                if( aChoice != [] ):
                    for i in range( len( aChoice ) ):
                        aChoice[i] = aChoice[i].strip(" \t,;.\n") # remove space or tabs at beginning or end of a choice
                        if( len( aChoice[i] ) < 1 ):
                            del aChoice[i]
                            i -= 1 # to parse the good one next loop
                if( len( aChoice ) > 0 ):
                    # check if there is a word which is already used for the default choices
                    for sWord in aChoice:
                        for aDefaultChoice in self.aDefaultChoices:
                            if( sWord in aDefaultChoice ):
                                raise Exception( "Error in choices list: You chose a word which is already used for default choices:\n" + str(sWord) + " is used for the default choice: " + str(aDefaultChoice[0]) )
                    # append the choice to the list if everything worked well
                    self.aChoices.append( aChoice )
                    self.aDialogChoices += aChoice
                    self.aChoiceIndexes.append( index )
                index += 1
        # check that there is at least one choice (a default one or not)
        if( len( self.aChoices ) < 1 ):
            raise Exception( "Error in choices list: It is empty. There is no default choice nor choice entered." )
        self.dChoices = self.removeUnauthorizedCharacters(self.aDialogChoices)
        self.sQuestion = [self.sQuestion]
# DIALOG ----------------------------------------------------------------------------------------------------

    def startDialog(self, activate = True):
        if self.bIsRunning:
            self.dialogIsRunning = True
            language = self.getLanguage()
            self.topics = []
            if not self.dialogIsLoaded:
                try:
                    for top in self.allTopicPaths:
                        topic = self.dialog._addDialogFromTopicBox(top, self.behaviorAbsolutePath())
                        self.topics.append(topic)
                        self.dialogIsLoaded = True
                except Exception as e:
                    print "Could not load topic " + str(e)
            if activate:
                try:
                    for top in self.topics:
                        if language in top.split("_")[-1]:
                            self.topic = top
                            self.guid = self.topic.split("_")[2]
                    self.dialog.setConcept("choices" + self.guid, language, self.aDialogChoices)
                    self.dialog.setConcept("question" + self.guid, language, self.sQuestion)
                    self.dialog.activateTopic(self.topic)
                    self.dialog.subscribe(self.getName())
                    thread.start_new_thread( self.loopLedsBrainTwinkle, () )
                except Exception as e:
                    print "Could not activate topic " + str(e)
                try:
                    self.memory.subscribeToEvent("Dialog/LastInput", self.getName(),"onDialogLastInput")
                    self.memory.subscribeToEvent("Dialog/NotSpeaking", self.getName(),"onDialogNotSpeaking")
                    self.memory.subscribeToEvent("Dialog/NotUnderstood", self.getName(),"onDialogNotUnderstood")
                except Exception as e:
                    print "Could not subscribe to event " + str(e)

    def stopDialog(self, unload=True):
        try:
            if unload:
                self.dialog.deactivateTopic(self.topic)
                for top in self.topics:
                    self.dialog.unloadTopic(top)
                self.dialogIsLoaded = False
            else:
                self.dialogIsRunning = False
            self.dialog.unsubscribe(self.getName())
        except Exception as e:
            print "Could not deactivate/unload topic " + str(e)
        try:
            self.memory.unsubscribeToEvent("Dialog/LastInput", self.getName())
            self.memory.unsubscribeToEvent("Dialog/NotSpeaking", self.getName())
            self.memory.unsubscribeToEvent("Dialog/NotUnderstood", self.getName())
        except Exception as e:
            print "Could not unsubscribe from Event " + str(e)

# DIALOG GENERATING --------------------------------------------------------------------------------------

    def generateTopicFile(self):
        self.directory = tempfile.mkdtemp()
        try:
            os.stat(self.directory)
        except:
            os.mkdir(self.directory)
        self.allTopicPaths = []
        for lang,dLang in self.langDict.iteritems():
            guid = str(uuid.uuid4())
            topicName = "dlg_choice_%s_%s.top" % (guid, dLang)
            topicPath = os.path.join(self.directory, topicName)
            self.allTopicPaths.append(topicPath)
            dialog = self.generateTopicContent(guid, dLang)
            with open(topicPath, 'w') as topic:
                topic.write(dialog)

    def generateTopicContent(self, guid, language):
        dialog = """topic: ~dlg_choice_%s_%s () \nlanguage: %s \ndynamic: question%s\ndynamic: choices%s\nu:(in:onActivation)  ~question%s \n\tu1:(~choices%s) $test=0 """ % (guid, language, language, guid, guid, guid, guid)
        return dialog

    def removeTopicFileDir(self):
        shutil.rmtree(self.directory)

# DIALOG OUTPUT PROCESSING --------------------------------------------------------------------------------------

    def onDialogLastInput(self, pDataName, pValue, pMessage):
        try:
            confidence = self.memory.getData("Dialog/Confidence")
        except:
            confidence = 0
        if pValue != "" and pValue in self.aDialogChoices:
            if confidence >= self.rConfirmationThreshold:
                self.sPreviousAnswer = pValue
                self.reactionWordUnderstood(pValue)
            else:
                self.stopDialog()
                self.sPreviousAnswer = pValue
                self.askConfirmation()
        else:
            if not self.bGoOut:
                if self.dialogIsRunning:
                    self.stopDialog(False)
                self.reactionNothingUnderstood()

    def onDialogNotSpeaking(self, pDataName, pValue, pMessage):
        if int(pValue) >= self.nTimeoutReco:
            if self.dialogIsRunning:
                self.stopDialog(False)
            self.sRecoInterruption = "timeout"

    def onDialogNotUnderstood(self, pDataName, pValue, pMessage):
        if self.dialogIsRunning:
            self.stopDialog(False)
        self.reactionNothingUnderstood()

# QUESTION-RECOGNITION-REACTION -----------------------------------------------------------------------------

    def questionRecognitionReaction(self):
        "Ask question, launch speech recognition and process answer."
        if not self.dialogIsRunning:
            self.startDialog(True)
        self.processRecoInterruption()

    def askConfirmation(self):
        "Ask question and initialize the speech recognition during the question to gain time in the interaction."
        self.bInConfirmation = True
        sentence = self.aAllSentences[self.tts.getLanguage()]["confirmation"][0]
        idTTS = -1
        sentenceToSay = sentence % self.sPreviousAnswer
        if( sentenceToSay != ""):
            idTTS = self.animSpeech.post.say( sentenceToSay )
            self.aIdsTTS.append( idTTS )
            self.logger.debug( "Robot says: " + str(sentenceToSay) )
        # prepare speech recognition
        aWordsRecognised = []
        aWordsRecognised.extend( self.asNegativeWords )
        aWordsRecognised.extend( self.asPositiveWords )
        sWordsRecognised = "You can say: "
        if( len( aWordsRecognised ) > 1 ):
            for i in range( len( aWordsRecognised ) - 1 ):
                sWordsRecognised += "'" + aWordsRecognised[i] + "', "
        if( len( aWordsRecognised ) > 0 ):
            sWordsRecognised += "'" + aWordsRecognised[len( aWordsRecognised ) - 1] + "'"
        sWordsRecognised += "."
        self.logger.debug( sWordsRecognised )
        self.bVocabularyLoaded = False
        # wait for the end of the TTS
        if( idTTS != -1 ):
            try:
                self.animSpeech.wait( idTTS, 0 )
            except:
                self.logger.debug( "Warning: Could not wait the animSpeech." )
        self.startDialog()

    def processRecoInterruption(self):
        "Process speech recognition interruption (timeout, action on tactile sensor, word said, etc...)"
        # wait for the end of the reaction (help, not understood, etc...)
        while( self.sRecoInterruption == "" ):
            time.sleep( 0.2 )
        self.logger.debug( "The speech recognition has been interrupted because of: " + str(self.sRecoInterruption) + "." )
        if( self.sRecoInterruption == "timeout" ): # if recognition interrupted by timeout
            try:
                # stop recognition
                self.stopDialog()
                self.bRecoIsWaitingForVoice = False
                self.bRecoIsHearingOrAnalysing = False
                self.logger.debug( "Speech recognition stopped." )
            except:
                pass
            if( self.bInConfirmation ): # if it was a confirmation question
                # if nothing has been said, we assume that the user agree
                self.bInConfirmation = False
                if( self.sPreviousAnswer in self.asHelpWords ): # if help asked
                    self.helpWhenAsked()
                elif( self.sPreviousAnswer in self.asRepeatWords ): # if repeat asked
                    self.repeatWhenNoQuestion()
                    # repeat the question
                else: # if not repeat nor help asked
                    self.goOut( self.sPreviousAnswer, "wordRecognised" )
            else:
                self.nCountNoReply += 1
                if( self.nCountNoReply >= self.nMaxCountNoReply ):
                    self.goOut( self.asExitWords[0], "timeout" )
                else:
                    self.startDialog()
                    self.sRecoInterruption = ""
                    self.processRecoInterruption()
        else:
            self.nCountNoReply = 0
        self.sRecoInterruption = ""

    def repeatWhenNoQuestion(self):
        "Robot's reaction when it is asked to repeat the question when there is no question."
        if self.dialogIsRunning:
            self.stopDialog(False)
        if( self.sQuestion == "" ):
            sentenceNoQuestion = self.aAllSentences[self.tts.getLanguage()]["noQuestion"][0]
            sentenceNoQuestion += self.enumerateChoices( True ) # True to ask that the introduction is played
            if( len( self.aChoices ) - len( self.aDefaultChoices ) == 0 ): # if there is no choice
                sentenceNoQuestion += self.enumerateDefaultChoices( True ) # True to ask that the introduction is played
            # launch TTS
            idTTS = -1
            if( sentenceNoQuestion != ""):
                if( self.bInTactileSensorMenu ):
                    idTTS = self.animSpeech.post.say( sentenceNoQuestion + "\\Pau=300\\" )
                else:
                    idTTS = self.animSpeech.post.say( sentenceNoQuestion )
                self.aIdsTTS.append( idTTS )
                self.logger.debug( "Robot says: " + str(sentenceNoQuestion) )
            # wait for the end of the TTS
            if( idTTS != -1 ):
                try:
                    self.animSpeech.wait( idTTS, 0 )
                except:
                    self.logger.debug( "Warning: Could not wait the TTS." )
        if not self.dialogIsRunning:
            self.bInTactileSensorMenu = False
            self.startDialog()

# RECO OUTPUT PROCESSING --------------------------------------------------------------------------------------

    def reactionWordUnderstood(self, word):
        "Reaction depending on the word recognised (help, repeat, word in choices, etc...) and its recognition confidence."
        self.headDefault()
        if( self.bInConfirmation ):
            self.bInConfirmation = False
            if( word in self.asNegativeWords ):
                # update number of failures
                self.nCountFailure += 1
                if( self.sPreviousAnswer in self.asHelpWords ):
                    if( self.nCountFailure >= self.nMaxCountFailure ): # if maximum number of failures
                        # skip the question
                        self.goOut( self.asExitWords[0], "notUnderstood" )
                else:
                    self.helpAfterFailure()
            else:
                if( (self.sPreviousAnswer in self.asHelpWords) or (word in self.asHelpWords) ):
                    self.helpWhenAsked()
                elif( self.sPreviousAnswer in self.asRepeatWords or (word in self.asRepeatWords) ):
                    self.repeatWhenNoQuestion()
                    # repeat the question
                else:
                    self.goOut( self.sPreviousAnswer, "wordRecognised" )
                self.sPreviousAnswer = ""
        else:
            self.sPreviousAnswer = word
            if( self.sPreviousAnswer in self.asHelpWords ):
                self.helpWhenAsked()
            elif( self.sPreviousAnswer in self.asRepeatWords ):
                self.repeatWhenNoQuestion()
                # repeat the question
            else:
                self.goOut( self.sPreviousAnswer, "wordRecognised" )
            self.sPreviousAnswer = ""

    def reactionNothingUnderstood(self):
        "Reaction when nothing has been understood or without an enough confidence."
        if( self.bInConfirmation ):
            # if the robot did not understand, we assume that the user agree
            self.bInConfirmation = False
            if( self.sPreviousAnswer in self.asHelpWords ): # if help asked
                self.helpWhenAsked()
            elif( self.sPreviousAnswer in self.asRepeatWords ): # if repeat asked
                self.repeatWhenNoQuestion()
                # repeat the question
            else: # if not repeat nor help asked
                self.goOut( self.sPreviousAnswer, "wordRecognised" )
        else:
            # update number of failures
            self.nCountFailure += 1
            if( self.nCountFailure <= 1 ): # if first failure
                sentence = self.aAllSentences[self.tts.getLanguage()]["notUnderstood"][0]
            else: # if second failure or more
                sentenceNotUnderstoodAnims = self.aAllSentences[self.tts.getLanguage()]["notUnderstoodAnims"]
                index = random.randint( 0, len( sentenceNotUnderstoodAnims ) - 1 )
                sentence = sentenceNotUnderstoodAnims[index]
            self.helpAfterFailure( sentence )

# HELP ------------------------------------------------------------------------------------------------------

    def enumerateChoices(self, bIntroToSay):
        "Enumerate choices (only the first word of each choice is taken into account)."
        sentenceHelpEnumChoices = self.aAllSentences[self.tts.getLanguage()]["helpEnumChoices"]
        sentenceHelpEnumMarks = self.aAllSentences[self.tts.getLanguage()]["enumMarks"]
        enumWords = ""
        maxNbEnumChoices = 3
        indexes = []
        for i in range( min(maxNbEnumChoices, len( self.aChoices ) - len( self.aDefaultChoices )) ):
            if( len( self.aChoices ) - len( self.aDefaultChoices ) <= maxNbEnumChoices ):
                index = len( self.aDefaultChoices ) + i
            else:
                index = random.randint( len( self.aDefaultChoices ), len( self.aChoices ) - 1 )
                while( index in indexes ):
                    index = random.randint( len( self.aDefaultChoices ), len( self.aChoices ) - 1 )
            indexes.append( index )
            if( len( indexes ) != 1 ): # if it is not the first choice
                if( len( indexes ) != min(maxNbEnumChoices, len( self.aChoices ) - len( self.aDefaultChoices )) ): # if it is not the last choice
                    enumWords += sentenceHelpEnumMarks[0]
                else:
                    enumWords += sentenceHelpEnumMarks[1]
            enumWords += self.aChoices[index][0]
        sentenceTemplate = sentenceHelpEnumChoices[2]
        if( len( self.aChoices ) - len( self.aDefaultChoices ) <= maxNbEnumChoices ): # if there are 3 or less choices
            sentenceTemplate = sentenceHelpEnumChoices[1]
        if( not bIntroToSay ):
            sentenceTemplate = sentenceHelpEnumChoices[3]
        if( len( self.aChoices ) - len( self.aDefaultChoices ) == 0 ): # if there is no choice
            sentence = sentenceHelpEnumChoices[0]
        else:
            sentence = sentenceTemplate % enumWords
        return sentence

    def enumerateDefaultChoices(self, bIntroToSay):
        "Enumerate default choices (only the first word of each choice is taken into account)."
        sentenceHelpEnumChoices = self.aAllSentences[self.tts.getLanguage()]["helpEnumChoices"]
        sentenceHelpEnumDefault = self.aAllSentences[self.tts.getLanguage()]["helpEnumDefault"]
        sentenceHelpEnumMarks = self.aAllSentences[self.tts.getLanguage()]["enumMarks"]
        enumWords = ""
        indexes = []
        for i in range( len( self.aDefaultChoices ) ):
            indexes.append( i )
            if( len( indexes ) != 1 ): # if it is not the first choice
                if( len( indexes ) != len( self.aDefaultChoices ) ): # if it is not the last choice
                    enumWords += sentenceHelpEnumMarks[0]
                else:
                    enumWords += sentenceHelpEnumMarks[1]
            enumWords += self.aDefaultChoices[i][0]
        sentenceTemplate = sentenceHelpEnumDefault[0]
        if( not bIntroToSay ):
            sentenceTemplate = sentenceHelpEnumChoices[3]
        if( len( self.aDefaultChoices ) == 0 ): # if there is no default choice
            sentence = ""
        else:
            sentence = sentenceTemplate % enumWords
        return sentence

    def explanationTactileSensor(self):
        "Explain the possible interaction with the tactile sensor."
        sentenceHelpTactile = self.aAllSentences[self.tts.getLanguage()]["helpTactile"]
        if( self.bInTactileSensorMenu ):
            sentence = sentenceHelpTactile[1]
        else:
            sentence = sentenceHelpTactile[0]
        return sentence

    def helpWhenAsked(self, sentence = ""):
        "Help when the user asked it: enumerate choices, enumerate default choices and explain tactile sensor possible interaction."
        if self.dialogIsRunning:
            self.stopDialog(False)
        if( not self.bInTactileSensorMenu ):
            # enumeration of choices
            sentence += self.enumerateChoices( True ) # True to ask that the introduction is played
            # enumeration of default choices
            sentence += self.enumerateDefaultChoices( True ) # True to ask that the introduction is played
        # explanation about alternative modality (tactil sensor, arm motion)
        sentence += self.explanationTactileSensor()
        # launch TTS
        idTTS = -1
        if( sentence != "" ):
            if( self.bInTactileSensorMenu ):
                idTTS = self.animSpeech.post.say( sentence + "\\Pau=300\\" )
                self.bInTactileSensorMenu = False
            else:
                idTTS = self.animSpeech.post.say( sentence )
            self.aIdsTTS.append( idTTS )
            self.logger.debug( "Robot says: " + str(sentence) )
        # wait for the end of the TTS
        if( idTTS != -1 ):
            try:
                self.animSpeech.wait( idTTS, 0 )
            except:
                self.logger.debug( "Warning: Could not wait the TTS." )
        # repeat the question
        if not self.dialogIsRunning:
            self.startDialog()

    def helpAfterFailure(self, sentence = ""):
        "Help when the speech recognition failed (nothing understood or incorrect answer understood)."
        if self.dialogIsRunning:
            self.stopDialog(False)
        if( self.nCountFailure < self.nMaxCountFailure ): # if reasonable number of failures
            if( self.bActivateHelpWhenFailure ):
                if( self.nCountFailure in [1, 2] ): # if first or second failure
                    # enumeration of choices, or default words if there is no choice
                    if( len( self.aChoices ) - len( self.aDefaultChoices ) > 0 ): # if there is at least one choice
                        sentence += self.enumerateChoices( self.nCountFailure == 1 ) # the introduction is played if it is the first failure
                    else:
                        sentence += self.enumerateDefaultChoices( self.nCountFailure == 1 ) # the introduction is played if it is the first failure
                    if( self.nCountFailure == 2 ): # if second failure
                        # explanation about alternative modality (tactil sensor, arm motion)
                        sentence += self.explanationTactileSensor()
                # launch TTS
                idTTS = -1
                if( sentence != "" ):
                    idTTS = self.animSpeech.post.say( sentence )
                    self.aIdsTTS.append( idTTS )
                    self.logger.debug( "Robot says: " + str(sentence) )
                # wait for the end of the TTS
                if( idTTS != -1 ):
                    try:
                        self.animSpeech.wait( idTTS, 0 )
                    except:
                        self.logger.debug( "Warning: Could not wait the TTS." )
            # repeat the question
            if not self.dialogIsRunning:
                self.startDialog()
        else: # if maximum number of failures
            # skip the question
            self.goOut( self.asExitWords[0], "notUnderstood" )

# LEDs ----------------------------------------------------------------------------------------------------

    def ledsChangeOnTactile(self):
        self.bBrainAnimPaused = True
        self.setLedsBrain( 0.5, int(rDuration * 1000) )
        time.sleep( 0.3 )
        self.setLedsBrain( 0., int(rDuration * 1000) )
        time.sleep( 0.2 )
        self.bBrainAnimPaused = False

    def loopLedsBrainTurn(self):
        self.setLedsBrain( 0., 500 )
        rIntensity = 0.5
        nTime = 50
        bAlreadyPaused = False
        while( self.bInTactileSensorMenu ):
            if( not self.bBrainAnimPaused ):
                if( self.nFront == 1 or self.nMiddle == 1 or self.nRear == 1 ):
                    if( not bAlreadyPaused ):
                        bAlreadyPaused = True
                        self.setLedsBrain( 0., 50 )
                else:
                    bAlreadyPaused = False
                    if( self.bActivateBrainLight ):
                        for i in range( 12 ):
                            if( not self.bBrainAnimPaused and self.dcm != None):
                                riseTime = self.dcm.getTime(nTime)
                                strDeviceName = self.getBrainLedName(i)
                                self.dcm.set( [ strDeviceName, "Merge",  [[ rIntensity, riseTime ]] ] )
                                time.sleep( nTime/1000. )
                                if( not self.bBrainAnimPaused ):
                                    self.dcm.set( [ strDeviceName, "Merge",  [[ 0.0, riseTime + int(nTime)/4 ]] ] )
            time.sleep( nTime/1000. )
        self.setLedsBrain( 0.5, 500 )

    def loopLedsBrainTwinkle(self):
        rIntensity = 0.5
        bOnStep = True
        bAlreadyPaused = False
        while( not self.bInTactileSensorMenu and self.bIsRunning ):
            if( not self.bBrainAnimPaused ):
                if( self.nFront == 1 or self.nMiddle == 1 or self.nRear == 1 ):
                    if( not bAlreadyPaused ):
                        bAlreadyPaused = True
                        self.setLedsBrain( 0., 50 )
                else:
                    bAlreadyPaused = False
                    if( bOnStep ):
                        self.setLedsBrain( rIntensity, 700 )
                        bOnStep = False
                    else:
                        self.setLedsBrain( 0.0, 700 )
                        bOnStep = True
            time.sleep( 1 )

    def setLedsBrain(self, rIntensity, rTimeMs):
        "One step of brain LEDS sequence (twinkle) when the robot is in speech recognition."
        if( self.bActivateBrainLight and self.dcm != None):
            riseTime = self.dcm.getTime( rTimeMs )
            for i in range( 12 ):
                strDeviceName = self.getBrainLedName(i)
                self.dcm.set( [ strDeviceName, "Merge",  [[ rIntensity, riseTime ]] ] )

# ANIMATIONS ----------------------------------------------------------------------------------------------

    def headDown(self):
        names = []
        times = []
        keys = []
        names.append("HeadPitch")
        times.append([1.24])
        keys.append([[0.392662, [3, -0.413333, 0], [3, 0, 0]]])

        names.append("HeadYaw")
        times.append([1.24])
        keys.append([[-0.027654, [3, -0.413333, 0], [3, 0, 0]]])
        try:
            self.motion.angleInterpolationBezier(names, times, keys)
            self.lastHeadPos = self.motion.getAngles(["HeadYaw","HeadPitch"], True)
        except BaseException, err:
          print err

    def headDefault(self):
        currentHeadPos = self.motion.getAngles(["HeadYaw","HeadPitch"], True)
        if currentHeadPos != self.lastHeadPos:
            return
        names = []
        times = []
        keys = []

        names.append("HeadPitch")
        times.append([1.2])
        keys.append([[-0.194861, [3, -0.4, 0], [3, 0, 0]]])

        names.append("HeadYaw")
        times.append([1.2])
        keys.append([[-0.00771196, [3, -0.4, 0], [3, 0, 0]]])

        try:
            self.motion.angleInterpolationBezier(names, times, keys)
        except BaseException, err:
          print err

# TACTILE SENSOR MENU -------------------------------------------------------------------------------------

    def onAlternativeModalityAction(self, p):
        "Process actions from alternative modalities (sequence from the tactile sensor, simple click on the torso button...)."
        if( not self.bIsRunning ): # if the box is not running
            return # then go out without doing a thing
        if( not self.bInTactileSensorMenu ): # if we are not in the tactile sensor menu (so if we are in the question-recognition-reaction loop)
            if( p in ["TapFront", "TapMiddle", "TapRear", "LongFront", "LongMiddle", "LongRear"] ):
                self.headDown()
                thread.start_new_thread(self.loopLedsBrainTurn, ())
                bTTSRunning = False # to know if TTS is running
                for idTTS in self.aIdsTTS:
                    if( self.animSpeech.isRunning( idTTS ) or self.tts.isRunning( idTTS )):
                        bTTSRunning = True
                if( bTTSRunning ): # if TTS is running
                    # skip the TTS
                    self.skipTTS()
                else: # if TTS was not running (so if in recognition)
                    # prepare to start the tactile sensor menu
                    self.bInTactileSensorMenu = True
                    # and stop the question-recognition-reaction loop
                    self.goOutOfQuestionRecoReaction()
                    self.sRecoInterruption = "onTactileSensor"
                    self.sayCurrentChoice()
                    # start counting timeout
                    self.rTimeWhenActionMadeInTactileMenu = time.time()
                    thread.start_new_thread( self.loopCheckTimeoutInTactileMenu, (self.rTimeWhenActionMadeInTactileMenu,) )
            elif( p in ["Tap", "CalmDown"] ):
                # skip the TTS
                self.skipTTS()
                # then stop everything and cancel the question
                self.goOut( self.asExitWords[0], "onTactileSensor" )
        else: # if we are in the tactile sensor menu
            self.rTimeWhenActionMadeInTactileMenu = -1.
            if( p in ["TapFront"] ):
                bTTSRunning = False # to know if TTS is running
                for idTTS in self.aIdsTTS:
                    if( self.animSpeech.isRunning( idTTS ) ):
                        bTTSRunning = True
                if( self.bIsSayingChoice or not bTTSRunning ): # else just skip the TTS (in the sayCurrentChoice function)
                    # change choice
                    self.nIndexChoice += 1
                    if( self.nIndexChoice >= len( self.aChoices ) ):
                        self.nIndexChoice = 0
                # say the choice in the tactile sensor menu
                self.sayCurrentChoice()
                self.timeoutManagingInTactileMenu()
            elif( p in ["TapRear"] ):
                bTTSRunning = False # to know if TTS is running
                for idTTS in self.aIdsTTS:
                    if( self.animSpeech.isRunning( idTTS )):
                        bTTSRunning = True
                if( self.bIsSayingChoice or not bTTSRunning ): # else just skip the TTS (in the sayCurrentChoice function)
                    # change choice
                    self.nIndexChoice -= 1
                    if( self.nIndexChoice < 0 ):
                        self.nIndexChoice = len( self.aChoices ) - 1
                # say the choice in the tactile sensor menu
                self.sayCurrentChoice()
                self.timeoutManagingInTactileMenu()
            elif( p in ["TapMiddle", "LongMiddle"] ):
                self.rTimeWhenActionMadeInTactileMenu = time.time()
                rTimeForThisAction = self.rTimeWhenActionMadeInTactileMenu
                bWasSayingChoice = self.bIsSayingChoice
                bTTSRunning = False # to know if TTS is running
                for idTTS in self.aIdsTTS:
                    if( self.animSpeech.isRunning( idTTS )):
                        bTTSRunning = True
                # skip the TTS if it is running
                self.skipTTS()
                if( bWasSayingChoice or not bTTSRunning ):
                    self.reactionWordUnderstood( self.aChoices[self.nIndexChoice][0] )
                    self.rTimeWhenActionMadeInTactileMenu = -1
                if( self.bIsRunning and rTimeForThisAction == self.rTimeWhenActionMadeInTactileMenu ): #$$$
                    self.rTimeWhenActionMadeInTactileMenu = -1.
                    # say the choice in the tactile sensor menu
                    self.sayCurrentChoice()
                    self.timeoutManagingInTactileMenu()
            elif( p == "LongFront" ):
                if( not self.bPressed ):
                    self.bPressed = True
                    bLastElementSaid = False
                    while( self.bPressed ):
                        if( self.nFront == 0 ):
                            self.bPressed = False
                            break
                        bTTSRunning = False # to know if TTS is running
                        for idTTS in self.aIdsTTS:
                            if( self.animSpeech.isRunning( idTTS )):
                                bTTSRunning = True
                        if( self.bIsSayingChoice or not bTTSRunning ):
                            # change choice
                            self.nIndexChoice += 1
                            if( self.nIndexChoice >= len( self.aChoices ) - 1 ):
                                self.nIndexChoice = len( self.aChoices ) - 1
                                if( not bLastElementSaid ):
                                    bLastElementSaid = True
                                    # say the choice in the tactile sensor menu
                                    thread.start_new_thread( self.sayCurrentChoice, () )
                            else:
                                # say the choice in the tactile sensor menu
                                thread.start_new_thread( self.sayCurrentChoice, () )
                        else:
                            if( self.nIndexChoice == len( self.aChoices ) - 1 ):
                                bLastElementSaid = True
                            # say the choice in the tactile sensor menu
                            thread.start_new_thread( self.sayCurrentChoice, () )
                        for i in range(8):
                            if( self.nFront == 0 ):
                                self.bPressed = False
                                break
                            time.sleep(0.1)
                    for idTTS in self.aIdsTTS:
                        if( self.animSpeech.isRunning( idTTS ) ):
                            try:
                                self.animSpeech.wait( idTTS, 0 )
                            except:
                                self.logger.debug( "Warning: Could not wait the TTS." )
                    self.timeoutManagingInTactileMenu()
            elif( p == "LongRear" ):
                if( not self.bPressed ):
                    self.bPressed = True
                    bFirstElementSaid = False
                    while( self.bPressed ):
                        if( self.nRear == 0 ):
                            self.bPressed = False
                            break
                        bTTSRunning = False # to know if TTS is running
                        for idTTS in self.aIdsTTS:
                            if( self.animSpeech.isRunning( idTTS )):
                                bTTSRunning = True
                        if( self.bIsSayingChoice or not bTTSRunning ):
                            # change choice
                            self.nIndexChoice -= 1
                            if( self.nIndexChoice <= 0 ):
                                self.nIndexChoice = 0
                                if( not bFirstElementSaid ):
                                    bFirstElementSaid = True
                                    # say the choice in the tactile sensor menu
                                    thread.start_new_thread( self.sayCurrentChoice, () )
                            else:
                                # say the choice in the tactile sensor menu
                                thread.start_new_thread( self.sayCurrentChoice, () )
                        else:
                            if( self.nIndexChoice == 0 ):
                                bFirstElementSaid = True
                            # say the choice in the tactile sensor menu
                            thread.start_new_thread( self.sayCurrentChoice, () )
                        for i in range(8):
                            if( self.nRear == 0 ):
                                self.bPressed = False
                                break
                            time.sleep(0.1)
                    for idTTS in self.aIdsTTS:
                        if( self.animSpeech.isRunning( idTTS ) ):
                            try:
                                self.animSpeech.wait( idTTS, 0 )
                            except:
                                self.logger.debug( "Warning: Could not wait the TTS." )
                    self.timeoutManagingInTactileMenu()
            elif( p in ["Tap", "CalmDown"] ):
                # then stop everything and cancel the question
                self.goOut( self.asExitWords[0], "onTactileSensor" )

    def sayCurrentChoice(self):
        "In the tactile sensor menu, make the robot say the current selected choice"
        self.bIsSayingChoice = True
        rTimeCurrent = time.time()
        self.rTimeLastChoiceSaid = rTimeCurrent
        # stop previous TTS
        self.skipTTS()
        # launch TTS
        idTTS = -1
        self.headDown()
        sentence = self.aChoices[ self.nIndexChoice ][0] + "?"
        idTTS = self.tts.post.say( sentence )
        self.aIdsTTS.append( idTTS )
        self.logger.debug( "Robot says: " + str(sentence) )
        if( idTTS != -1 ):
            try:
                self.animSpeech.wait( idTTS, 0 )
            except:
                self.logger.debug( "Warning: Could not wait the TTS." )
        if( self.rTimeLastChoiceSaid == rTimeCurrent ):
            self.rTimeLastChoiceSaid = -1.
            self.bIsSayingChoice = False

    def timeoutManagingInTactileMenu(self):
        # check if there has been an other action with tts made while this one was processed
        bTTSRunning = False # to know if TTS is running
        for idTTS in self.aIdsTTS:
            if( self.animSpeech.isRunning( idTTS )):
                bTTSRunning = True
        if( not bTTSRunning ):
            # start counting timeout
            self.rTimeWhenActionMadeInTactileMenu = time.time()
            thread.start_new_thread( self.loopCheckTimeoutInTactileMenu, (self.rTimeWhenActionMadeInTactileMenu,) )

    def loopCheckTimeoutInTactileMenu(self, rTimeForThisAction):
        nTimeout = time.time() + self.nTimeoutTactile
        if( self.rTimeWhenActionMadeInTactileMenu == rTimeForThisAction ):
            while( time.time() < nTimeout and self.rTimeWhenActionMadeInTactileMenu == rTimeForThisAction and self.bIsRunning ):
                time.sleep( 0.1 )
            if( self.rTimeWhenActionMadeInTactileMenu != rTimeForThisAction ):
                self.nCountNoReply = 0
            elif( self.bIsRunning ):
                self.rTimeWhenActionMadeInTactileMenu = -1.
                self.nCountNoReply += 1
                if( self.nCountNoReply >= self.nMaxCountNoReply ):
                    self.goOut( self.asExitWords[0], "timeout" )
                else:
                    bTTSRunning = False # to know if TTS is running
                    for idTTS in self.aIdsTTS:
                        if( self.animSpeech.isRunning( idTTS )):
                            bTTSRunning = True
                    if( not bTTSRunning ):
                        # say the choice in the tactile sensor menu
                        self.sayCurrentChoice()
                        # start counting timeout
                        self.rTimeWhenActionMadeInTactileMenu = time.time()
                        thread.start_new_thread( self.loopCheckTimeoutInTactileMenu, (self.rTimeWhenActionMadeInTactileMenu,) )

# TACTILE SENSOR HANDLER -------------------------------------------------------------------------------

    def initSeqDetected(self):
        "Initialize the sequence handler."
        self.bSeqStarted = False
        self.aDetectedSeqs = []
        self.aDetectedSeqs.extend(self.aSeqs)
        for seq in self.aDetectedSeqs:
            seq["index"] = 0
            seq["previousStepTime"] = 0

    def convertToArrayOfPossibleStates(self, states):
        "Check if the states described in the sequences using a string are in the right syntax, and then convert them to an array of the possible states."
        aStates = []
        aStates3 = [[1, 1, 1]]
        aStates2 = [[0, 1, 1], [1, 0, 1], [1, 1, 0]]
        aStates1 = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        aStates0 = [[0, 0, 0]]
        try:
            if( int(states) == states ): # if states is an integer
                states = str(states)
        except:
            pass
        if( self.isString(states) ):
            if( not states in ["*", "0+", "0", "0-", "1+", "1", "1-", "2+", "2", "2-", "3+", "3", "3-", "F+", "F", "F-", "M+", "M", "M-", "R+", "R", "R-"] ):
                raise Exception( "Error in sequences states description syntax: description expected in " + str(["*", "0+", "0", "0-", "1+", "1", "1-", "2+", "2", "2-", "3+", "3", "3-", "F+", "F", "F-", "M+", "M", "M-", "R+", "R", "R-"]) + " but " + str(p) + " found with this type: " + str(type(p)) )
            if( states in ["*", "0+", "1+", "2+", "3+", "3", "3-", "F+", "M+", "R+"] ):
                aStates.extend(aStates3)
            if( states in ["*", "0+", "1+", "2+", "2", "2-", "3-"] ):
                aStates.extend(aStates2)
            if( states in ["*", "0+", "1+", "1", "1-", "2-", "3-"] ):
                aStates.extend(aStates1)
            if( states in ["*", "0+", "0", "0-", "1-", "2-", "3-", "F-", "M-", "R-"] ):
                aStates.extend(aStates0)
            if( states in ["F", "F+", "F-"] ):
                aStates.append([1, 0, 0])
            if( states in ["M", "M+", "M-"] ):
                aStates.append([0, 1, 0])
            if( states in ["R", "R+", "R-"] ):
                aStates.append([0, 0, 1])
            if( states in ["F+", "M+"] ):
                aStates.append([1, 1, 0])
            if( states in ["R+", "M+"] ):
                aStates.append([0, 1, 1])
            if( states in ["F+", "R+"] ):
                aStates.append([1, 0, 1])
        elif( self.isArray(states) ):
            if( self.isArray(states[0]) ):
                aStates = states
            elif( int(states[0]) == states[0] ):
                aStates = [states]
            else:
                raise Exception( "Error in sequences states description syntax: description expected in " + str(["*", "0+", "0", "0-", "1+", "1", "1-", "2+", "2", "2-", "3+", "3", "3-", "F+", "F", "F-", "M+", "M", "M-", "R+", "R", "R-"]) + " but " + str(p) + " found with this type: " + str(type(p)) )
        else:
            raise Exception( "Error in sequences states description syntax:\nstring, array or int expected but " + str(type(p)) + " found" )
        return aStates

    def checkIfSeqsCorrespondingLeft(self, param):
        "If the sequence handler is done (there is no sequence detected left or the first in the list corresponds), then reinitialize the sequence handler, and give the corresponding sequence if there is one."
        if( self.aDetectedSeqs == [] ):
            # then no sequence corresponding in the list
            self.initSeqDetected()
        else:
            if( self.aDetectedSeqs[0]["index"] == -1 ): # if first sequence in left ones corresponds
                # then it is this sequence which is played
                thread.start_new_thread( self.onAlternativeModalityAction, (self.aDetectedSeqs[0]["name"],) )
                self.initSeqDetected()
        self.mutexCheckIfSeqsCorrespondingLeft.unlock()

    def loopCheckTimeoutMax(self, nTimeoutMax, seq, currentState, currentTime):
        "When timeout ellapsed, check the sequence status and process it."
        nPreviousIndex = seq["index"]
        time.sleep(nTimeoutMax + 0.1)
        aSeqsTemp = []
        aSeqsTemp.extend( self.aDetectedSeqs )
        currentState = [self.nFront, self.nMiddle, self.nRear]
        currentTime = time.time()
        if( nPreviousIndex == seq["index"] and not self.mutexProcessCurrentState.test() and not (1 in currentState) ): # if no change in the sequence step but timeout ellapsed and sequence handler is not processing (so if there is no action from the user and the sequence is still at the same point)
            if( seq in aSeqsTemp and seq["index"] != -1 ): # but if sequence is still in the possible ones and not completed
                if( currentState in seq["statesAndTimeout"][seq["index"]] ): # last check if the current state corresponds to the next one
                    # then we go to the next step
                    seq["previousStepTime"] = currentTime
                    seq["index"] += 2
                    if( seq["index"] > len( seq["statesAndTimeout"] ) ): # if there is no more step
                        seq["index"] = -1 # then the sequence is completed
                    else: # if there is at least one step left
                        nTimeoutMin = 0
                        nTimeoutMax = 5
                        if( self.isArray(seq["statesAndTimeout"][seq["index"]-1]) ):
                            if( seq["statesAndTimeout"][seq["index"]-1][0] < 0 ):
                                nTimeoutMin = - seq["statesAndTimeout"][seq["index"]-1][0]
                                nTimeoutMax = seq["statesAndTimeout"][seq["index"]-1][1]
                            else:
                                nTimeoutMax = seq["statesAndTimeout"][seq["index"]-1][0]
                                nTimeoutMin = - seq["statesAndTimeout"][seq["index"]-1][1]
                        else:
                            if( seq["statesAndTimeout"][seq["index"]-1] < 0 ):
                                nTimeoutMin = - seq["statesAndTimeout"][seq["index"]-1]
                            else:
                                nTimeoutMax = seq["statesAndTimeout"][seq["index"]-1]
                        thread.start_new_thread( self.loopCheckTimeoutMax, (nTimeoutMax, seq, currentState, currentTime) )
                else:
                    # then remove the sequence from the possible ones
                    aSeqsTemp.remove(seq)
                    self.aDetectedSeqs = aSeqsTemp
                self.mutexCheckIfSeqsCorrespondingLeft.lock( self.checkIfSeqsCorrespondingLeft, None )

    def loopCheckTimeoutMin(self, nTimeoutMin, seq):
        "Wait that the minimum timeout ellapse to check if the new tactile sensor state corresponds to the expected one for this sequence."
        if( nTimeoutMin != 0 ):
            nPreviousIndex = seq["index"]
            time.sleep(nTimeoutMin - time.time() + seq["previousStepTime"])
            currentTime = time.time()
            currentState = [self.nFront, self.nMiddle, self.nRear]
            self.mutexProcessCurrentState.lock( self.processCurrentState, [0, currentState, currentTime] )

    def updateDetectedSeqs(self, seq, aSeqsTemp, currentState, currentTime):
        "Update a detected sequence."
        if( seq["index"] > 0 ): # if not the first step
            nTimeoutMin = 0
            nTimeoutMax = 5
            if( self.isArray(seq["statesAndTimeout"][seq["index"]-1]) ):
                if( seq["statesAndTimeout"][seq["index"]-1][0] < 0 ):
                    nTimeoutMin = - seq["statesAndTimeout"][seq["index"]-1][0]
                    nTimeoutMax = seq["statesAndTimeout"][seq["index"]-1][1]
                else:
                    nTimeoutMax = seq["statesAndTimeout"][seq["index"]-1][0]
                    nTimeoutMin = - seq["statesAndTimeout"][seq["index"]-1][1]
            else:
                if( seq["statesAndTimeout"][seq["index"]-1] < 0 ):
                    nTimeoutMin = - seq["statesAndTimeout"][seq["index"]-1]
                else:
                    nTimeoutMax = seq["statesAndTimeout"][seq["index"]-1]
            if( currentTime > nTimeoutMax + seq["previousStepTime"] ): # if timeout of this step ellapsed
                aSeqsTemp.remove(seq) # then it is not this sequence which is played
            elif( not (currentState in seq["statesAndTimeout"][seq["index"]]) ): # if the current state does not correspond to one of the described ones but the timeout of this step did not ellaspe
                # then we check that this state could be an intermediate one
                aIntermediateStates = [[], [], []]
                for i in range( len( currentState ) ):
                    for j in range( len( seq["statesAndTimeout"][seq["index"]] ) ):
                        aIntermediateStates[i].append( seq["statesAndTimeout"][seq["index"]][j][i] )
                    for j in range( len( seq["statesAndTimeout"][seq["index"]-2] ) ):
                        aIntermediateStates[i].append( seq["statesAndTimeout"][seq["index"]-2][j][i] )
                bIsIntermediate = True
                for i in range( len( currentState ) ):
                    bIsIntermediate = bIsIntermediate and ( currentState[i] in aIntermediateStates[i] )
                if( not bIsIntermediate ):
                    aSeqsTemp.remove(seq) # then it is not this sequence which is played
            else: # if the current state correspond to one of the described ones
                if( currentTime > nTimeoutMin + seq["previousStepTime"] ): # if the minimum time to wait the next step is ellapsed
                    # then we go to the next step
                    seq["previousStepTime"] = currentTime
                    seq["index"] += 2
                    if( seq["index"] > len( seq["statesAndTimeout"] ) ): # if there is no more step
                        seq["index"] = -1 # then the sequence is completed
                    else: # if there is at least one step left
                        # start clock to timeout
                        nTimeoutMin = 0
                        nTimeoutMax = 5
                        if( self.isArray(seq["statesAndTimeout"][seq["index"]-1]) ):
                            if( seq["statesAndTimeout"][seq["index"]-1][0] < 0 ):
                                nTimeoutMin = - seq["statesAndTimeout"][seq["index"]-1][0]
                                nTimeoutMax = seq["statesAndTimeout"][seq["index"]-1][1]
                            else:
                                nTimeoutMax = seq["statesAndTimeout"][seq["index"]-1][0]
                                nTimeoutMin = - seq["statesAndTimeout"][seq["index"]-1][1]
                        else:
                            if( seq["statesAndTimeout"][seq["index"]-1] < 0 ):
                                nTimeoutMin = - seq["statesAndTimeout"][seq["index"]-1]
                            else:
                                nTimeoutMax = seq["statesAndTimeout"][seq["index"]-1]
                        thread.start_new_thread( self.loopCheckTimeoutMin, (nTimeoutMin, seq) )
                        thread.start_new_thread( self.loopCheckTimeoutMax, (nTimeoutMax, seq, currentState, currentTime) )
                else: # if the minimum time to wait the next step is not ellapsed
                    # then we are going to wait until it is to check then
                    thread.start_new_thread( self.loopCheckTimeoutMin, (nTimeoutMin, seq) )
        elif( seq["index"] == 0 ): # for the first step
            if( currentState in seq["statesAndTimeout"][seq["index"]] ): # if the current state correspond to one of the described ones
                # then we go to the next step
                seq["previousStepTime"] = currentTime
                seq["index"] += 2
                if( seq["index"] > len( seq["statesAndTimeout"] ) ): # if there is no more step
                    seq["index"] = -1 # then the sequence is completed
                else: # if there is at least one step left
                    # start clock to timeout
                    nTimeoutMin = 0
                    nTimeoutMax = 5
                    if( self.isArray(seq["statesAndTimeout"][seq["index"]-1]) ):
                        if( seq["statesAndTimeout"][seq["index"]-1][0] < 0 ):
                            nTimeoutMin = - seq["statesAndTimeout"][seq["index"]-1][0]
                            nTimeoutMax = seq["statesAndTimeout"][seq["index"]-1][1]
                        else:
                            nTimeoutMax = seq["statesAndTimeout"][seq["index"]-1][0]
                            nTimeoutMin = - seq["statesAndTimeout"][seq["index"]-1][1]
                    else:
                        if( seq["statesAndTimeout"][seq["index"]-1] < 0 ):
                            nTimeoutMin = - seq["statesAndTimeout"][seq["index"]-1]
                        else:
                            nTimeoutMax = seq["statesAndTimeout"][seq["index"]-1]
                    thread.start_new_thread( self.loopCheckTimeoutMin, (nTimeoutMin, seq) )
                    thread.start_new_thread( self.loopCheckTimeoutMax, (nTimeoutMax, seq, currentState, currentTime) )
            else: # if the current state does not correspond to the first described
                aSeqsTemp.remove(seq) # then it is not this sequence which has just been started

    def updateSeqsHandler(self, currentState, currentTime):
        "Update list of detected sequences."
        aSeqsTemp = []
        aSeqsTemp.extend( self.aDetectedSeqs )
        for seq in self.aDetectedSeqs:
            self.updateDetectedSeqs( seq, aSeqsTemp, currentState, currentTime )
        self.aDetectedSeqs = aSeqsTemp
        self.mutexCheckIfSeqsCorrespondingLeft.lock( self.checkIfSeqsCorrespondingLeft, None )

    def processCurrentState(self, param):
        "Process the current tactile sensor state."
        pValue = param[0]
        currentState = param[1]
        currentTime = param[2]
        if( pValue == 1 and not self.bSeqStarted ):
            self.bSeqStarted = True
            for seq in self.aDetectedSeqs:
                seq["previousStepTime"] = currentTime
        # update sequences handler
        if( self.bSeqStarted ):
            self.updateSeqsHandler(currentState, currentTime)
        self.mutexProcessCurrentState.unlock()

    def onFrontTactilTouched(self, param):
        "Handle an action (touch or release) on the front tactile sensor."
        pValue = param[0]
        currentTime = param[1]
        currentState = [pValue, self.nMiddle, self.nRear]
        self.nFront = pValue
        self.mutexProcessCurrentState.lock( self.processCurrentState, [pValue, currentState, currentTime] )
        self.mutexTactilTouched.unlock()

    def onMiddleTactilTouched(self, param):
        "Handle an action (touch or release) on the middle tactile sensor."
        pValue = param[0]
        currentTime = param[1]
        currentState = [self.nFront, pValue, self.nRear]
        self.nMiddle = pValue
        self.mutexProcessCurrentState.lock( self.processCurrentState, [pValue, currentState, currentTime] )
        self.mutexTactilTouched.unlock()

    def onRearTactilTouched(self, param):
        "Handle an action (touch or release) on the rear tactile sensor."
        pValue = param[0]
        currentTime = param[1]
        currentState = [self.nFront, self.nMiddle, pValue]
        self.nRear = pValue
        self.mutexProcessCurrentState.lock( self.processCurrentState, [pValue, currentState, currentTime] )
        self.mutexTactilTouched.unlock()

    def onTactilTouched(self, pDataName, pValue, pMessage):
        "Handle an action (touch or release) on the tactile sensor."
        self.stopDialog(False)
        self.nCountNoReply = 0
        self.lastTimeoutVal = 0
        self.mutexTactilTouched.lock( getattr( self, "on" + pDataName ), [pValue, time.time()] )

# OUTPUTS ACTIVATION --------------------------------------------------------------------------------------

    def goOut(self, outputName, cancelReason = ""):
        "Activate the right output (a choice output or the other output)."
        try:
            self.memory.unsubscribeToEvent( "FrontTactilTouched", self.getName() )
            self.memory.unsubscribeToEvent( "MiddleTactilTouched", self.getName() )
            self.memory.unsubscribeToEvent( "RearTactilTouched", self.getName() )
        except:
            pass
        self.bInTactileSensorMenu = False
        self.bIsRunning = False
        self.goOutOfQuestionRecoReaction()

        if( outputName in self.asExitWords ):
            try:
                self.other( cancelReason )
                self.logger.debug( "Output 'other' stimulated because cancel asked: " + str(cancelReason) + "." )
            except:
                try:
                    self.onStopped( cancelReason )
                    self.logger.debug( "Output 'onStopped' stimulated because cancel asked: " + str(cancelReason) + "." )
                except:
                    try:
                        self.onStopped()
                        self.logger.debug( "Output 'onStopped' stimulated because cancel asked." )
                    except:
                        choregraphe = ALProxy( "ALChoregraphe" )
                        choregraphe.onPythonError( self.getName(), "goOut", "Invalid output: the main output name needs to be 'other', and it needs to be dynamic (because it can be either a string, or an integer)." )
        else:
            nOutput = -1
            for i in range( len (self.aChoices) - len (self.aDefaultChoices) ):
                if( nOutput == -1 ):
                    if( outputName in self.aChoices[i+len( self.aDefaultChoices )] ):
                        nOutput = i
            if( nOutput != -1):
                if( self.bExternChoices ):
                    if( self.bRepeatValidatedChoice ):
                        self.skipTTS()
                        self.animSpeech.say( outputName )
                    try:
                        self.other( self.aChoiceIndexes[nOutput] )
                        self.logger.debug( "Output 'other' stimulated with: " + str(self.aChoiceIndexes[nOutput]) + " (corresponding to the choice '" + str(self.aChoices[nOutput+len( self.aDefaultChoices )][0]) + "')." )
                    except:
                        try:
                            self.onStopped( self.aChoiceIndexes[nOutput] )
                            self.logger.debug( "Output 'onStopped' stimulated with: " + str(self.aChoiceIndexes[nOutput]) + " (corresponding to the choice '" + str(self.aChoices[nOutput+len( self.aDefaultChoices )][0]) + "')." )
                        except:
                            choregraphe = ALProxy( "ALChoregraphe" )
                            choregraphe.onPythonError( self.getName(), "goOut", "Invalid type of output: using the input 'choicesList', the main output needs to be dynamic (because it can be either a string, or an integer)." )
                else:
                    if( self.bRepeatValidatedChoice ):
                        self.skipTTS()
                        self.animSpeech.say( outputName )
                    try:
                        func = getattr( self, "output_" + str(self.aChoiceIndexes[nOutput]+1) ) #+1 because the first one is output_1 corresponding to the element 0 in the list.
                        func(outputName)
                    except:
                        choregraphe = ALProxy( "ALChoregraphe" )
                        choregraphe.onPythonError( self.getName(), "goOut", "Invalid output: the output 'output_" + str(self.aChoiceIndexes[nOutput]+1) + "' was expected to be stimulated with: " + str(outputName) + " but could not." )

# UNLOAD --------------------------------------------------------------------------------------------------

    def goOutOfQuestionRecoReaction(self):
        "Set some variables to go out of the question-recognition-reaction loop and reinitialize other variables which are going to be used again only on the next start of this box."
        self.bGoOut = True
        self.bMustStop = True
        self.nCountFailure = 0
        self.nCountNoReply = 0
        self.bInConfirmation = False
        self.bVocabularyLoaded = False
        self.skipTTS()
        if self.dialogIsRunning:
            self.stopDialog(False)
        for idTTS in self.aIdsTTS:
            try:
                self.aIdsTTS.remove( idTTS )
            except:
                self.logger.debug( "Warning: The task ID corresponding to the Text-To-Speech could not have been removed from the ID tasks list." )

    def onUnload(self):
        "Reinitialize variables to default state."
        self.goOutOfQuestionRecoReaction()
        self.stopDialog()
        language = self.getLanguage()
        #reset concepts to reduce loading time
        try:
            self.dialog.setConcept("choices" + self.guid, language, [])
            self.dialog.setConcept("question" + self.guid, language, [])
        except Exception as e:
            print "Could not empty concept " + str(e)
        try:
            self.removeTopicFileDir()
        except Exception as e:
            print "Could not remove temporary topic file directory " + str(e)
        try:
            self.memory.unsubscribeToEvent( "FrontTactilTouched", self.getName() )
            self.memory.unsubscribeToEvent( "MiddleTactilTouched", self.getName() )
            self.memory.unsubscribeToEvent( "RearTactilTouched", self.getName() )
        except:
            pass
        self.bIsRunning = False