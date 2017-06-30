# -*- coding: utf-8 -*-
"""
Created on Thu May 14 16:26:29 2015

@author: Ian Spielman
"""
 

# todo: implement nice shutdown of tab widget that shutdown all the tabs
# one-by-one

import os 

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import pyqtSignal


from PyQt4.Qsci import QsciScintilla, QsciLexerPython, QsciCommand
from qtutils import UiLoader

class SimplePythonEditor(QtGui.QWidget):

    # New signals
    filenameTrigger = pyqtSignal(str)

    def __init__(self, parent=None):
        super(SimplePythonEditor, self).__init__()

        loader = UiLoader()
        loader.registerCustomWidget(SimplePythonEditorTextField)
        self._ui = loader.load('simplepythoneditor.ui', self)
                
        # Connections
        self._ui.save_toolButton.clicked.connect(self.on_save)
        self._ui.sendFilename_toolButton.clicked.connect(self.on_filenameTrigger)
        self._ui.editor_tabWidget.tabCloseRequested.connect(self.closeTab)

        # restart the find-replace when anything is changed
        self._ui.find_text_lineEdit.textChanged.connect(self.restart_find_replace_and_search)
        self._ui.search_forward_toolButton.toggled.connect(self.restart_find_replace)
        self._ui.case_sensitive_checkBox.toggled.connect(self.restart_find_replace)
        self._ui.wrap_search_checkBox.toggled.connect(self.restart_find_replace)
        self._ui.whole_word_checkBox.toggled.connect(self.restart_find_replace)
        self._ui.do_search_pushButton.clicked.connect(self.on_find_replace)        

        self._ui.goto_line_done_toolButton.clicked.connect(self.toggle_goto_line)
        self._ui.goto_line_spinBox.editingFinished.connect(self.on_goto_line)
        
        # Hide optoinal functions
        self._ui.goto_line_groupBox.hide()
        self._ui.find_replace_groupBox.hide()


    #        
    # Functionality special to this object
    #

    @property
    def _currentEditor(self):
        return self._ui.editor_tabWidget.currentWidget()

    @property 
    def _currentIndex(self):
        return self._ui.editor_tabWidget.currentIndex()
        
    def createTab(self):
        """
        Creates a new tab with an editor in it
        """
        editor = SimplePythonEditorTextField(self._ui.editor_tabWidget)
        index = self._ui.editor_tabWidget.addTab(editor, editor.name)
        self._ui.editor_tabWidget.setCurrentIndex(index)
    
    def closeTab(self, index):
        """
        closedown the tab with index
        """
        widget = self._ui.editor_tabWidget.widget(index)

        # see if this widget is changed and wants to close:
        if widget._changed:
            # see if user wants to save changed file
            msgBox = QtGui.QMessageBox(self)
            
            msgBox.setText("The document has been modified.")
            msgBox.setInformativeText("Do you want to save your changes?")
            msgBox.setStandardButtons(QtGui.QMessageBox.Save | QtGui.QMessageBox.Discard | QtGui.QMessageBox.Cancel)
            msgBox.setDefaultButton(QtGui.QMessageBox.Save)
            reply = msgBox.exec_()
                
            if reply == QtGui.QMessageBox.Cancel:
                return
            
            if reply == QtGui.QMessageBox.Save:
                widget.on_save(True)

        self._ui.editor_tabWidget.removeTab(index)
        
        # Inform child to shutdown need to be widget at index
        if widget:
            widget.close()
            widget.deleteLater()    
    
    #
    # Functionality passed on from editor children
    #

    def setText(self, text, *args, **kwargs):   
        """
        sets the text contents of a new tab
        """
        self.createTab()
        self._currentEditor.filename = ''
        self._currentEditor.setText(text, *args, **kwargs)

    def text(self):
        """
        Returns text contents of current tab
        """
        if self._currentEditor:
            return self._currentEditor.text()

    def on_filenameTrigger(self, checked=True):
        """
        When this is called emit a signal containg the current filename
        """
        if self._currentEditor:
            self.filenameTrigger.emit(self._currentEditor.filename)

    def on_new(self):
        self.createTab()        

    def on_open_named(self, filename=''):
                
        # Check to see if filename exists
        tabs = len(self._ui.editor_tabWidget)
        for index in range(tabs):
            widget = self._ui.editor_tabWidget.widget(index)
            if widget.filename == filename:
                self._ui.editor_tabWidget.setCurrentIndex(index)
                return
        
        self.createTab()
        self._currentEditor.on_open_named(filename)        

    def on_open(self, checked=True):
        if self._currentEditor:
            path = self._currentEditor.folder
        else:
            path = ''
            
        filename = QtGui.QFileDialog.getOpenFileName(self,
                                                     'Select python file',
                                                     path,
                                                     "Python files (*.py)")
        # Convert to standard platform specific path, otherwise Qt likes forward slashes:
        filename = os.path.abspath(filename)
 
        self.on_open_named(filename=filename)

    def on_save(self, checked=True):
        if self._currentEditor:
            self._currentEditor.on_save(checked)
        
    def on_save_as(self, checked=True):
        if self._currentEditor:
            self._currentEditor.on_save_as(checked)

    def toggle_find_replace(self, checked=True):
        if self._ui.find_replace_groupBox.isVisible():
            self._ui.find_replace_groupBox.hide()
        else:        
            self._ui.find_replace_groupBox.show()

    def on_goto_line(self):
        if self._currentEditor:
            line = self.goto_line_spinBox.value()-1 # zero indexed
            self._currentEditor.setCursorPosition(line, 0)
    
    def toggle_goto_line(self, checked=True):
        if self._ui.goto_line_groupBox.isVisible():
            self._ui.goto_line_groupBox.hide()
        else:        
            self._ui.goto_line_groupBox.show()

    def restart_find_replace(self):
        if self._currentEditor:
            self._currentEditor.restart_find_replace()

    def restart_find_replace_and_search(self):
        """
        Do a new search
        """
        self.restart_find_replace()
        self.on_find_replace()

    def on_find_replace(self):
        if self._currentEditor:
            text = self.find_text_lineEdit.text()
            self._currentEditor.on_find_replace(text,
                    replace_text=self._ui.replace_text_lineEdit.text(),
                    replace=self._ui.replace_checkBox.isChecked(),
                    replace_all=self._ui.replace_all_checkBox.isChecked(),
                    case_sensitive=self._ui.case_sensitive_checkBox.isChecked(),
                    whole_word=self._ui.whole_word_checkBox.isChecked(), 
                    wrap_search=self._ui.wrap_search_checkBox.isChecked(),
                    forward=self._ui.search_forward_toolButton.isChecked()
                    )

class SimplePythonEditorTextField(QsciScintilla):

    ARROW_MARKER_NUM = 8

    def __init__(self, parent=None):
        super(SimplePythonEditorTextField, self).__init__(parent)

        # defaults
        self._filename = ''
        self._folder = ''
        self._changed = False
        self._parent = parent
        self._unsearched = True

        # Connect some actions
        self.textChanged.connect(self.on_textChanged)

        # disk file monitor
        self.fileWatcher = QtCore.QFileSystemWatcher()
        self.fileWatcher.fileChanged.connect(self.on_fileChanged)

        #
        # Setup the editor 
        #

        # Set the default font
        font = QtGui.QFont()
        font.setFamily('Courier')
        font.setFixedPitch(True)
        font.setPointSize(9.5)
        self.setFont(font)
        self.setMarginsFont(font)

        # Margin 0 is used for line numbers
        fontmetrics = QtGui.QFontMetrics(font)
        self.setMarginsFont(font)
        self.setMarginWidth(0, fontmetrics.width("0000") + 6)
        self.setMarginLineNumbers(0, True)
        self.setMarginsBackgroundColor(QtGui.QColor("#cccccc"))

        # Brace matching: enable for a brace immediately before or after
        # the current position
        #
        self.setBraceMatching(QsciScintilla.SloppyBraceMatch)

        # Current line visible with special background color
        self.setCaretLineVisible(True)
        self.setCaretLineBackgroundColor(QtGui.QColor("#ffe4e4"))

        # Unix end of line chars
        self.setEolMode(self.EolUnix)
        
        # Set Python lexer
        # Set style for Python comments (style number 1) to a fixed-width
        # courier.
        #
        lexer = QsciLexerPython()
        lexer.setDefaultFont(font)
        lexer.setFoldCompact(False) # so folding ends at the end of functions
                                    # not at the start of the next object
        self.setLexer(lexer)
        self.SendScintilla(QsciScintilla.SCI_STYLESETFONT, 1, 'Courier')

        # unset control charaters I need access to

        commands = self.standardCommands()

        # free ctrl-L to goto line        
        command = commands.find(QsciCommand.LineCut)
        command.setKey(0)

        # Set python tabs
        self.setTabIndents(True)
        self.setTabWidth(4)
        self.setIndentationsUseTabs(False)

        #AutoIndentation
        self.setAutoIndent(True)
        self.setIndentationGuides(True)
        self.setIndentationWidth(4)

        # Code folding
        self.setMarginWidth(1, 14)
        self.setFolding(QsciScintilla.BoxedTreeFoldStyle)

        # Edge Mode shows a red vetical bar at 80 chars
        self.setEdgeMode(QsciScintilla.EdgeLine)
        self.setEdgeColumn(80)
        # self.setEdgeColor(QtGui.QColor("#FF0000"))

        # Don't want to see the horizontal scrollbar at all
        # Use raw message to Scintilla here (all messages are documented
        # here: http://www.scintilla.org/ScintillaDoc.html)
        self.SendScintilla(QsciScintilla.SCI_SETHSCROLLBAR, 1)

        # not too small
        self.setMinimumSize(fontmetrics.averageCharWidth()*92, 450)

    #
    # Helpers
    #

    #
    # Control enclosing tab widget to set the labels indicating file changed
    #

    def getIndex(self):
        return self._parent.indexOf(self)
        
    def setParentTitle(self, text):
        self._parent.setTabText(self.getIndex(), text)

    #
    # setup monitor for file name changed, and block direct changes to 
    # self.filename 
    #

    @property
    def name(self):
        
        basename = os.path.basename(self.filename)
        
        if not basename:
            basename = '<<new>>'
            
        if self._changed:
            basename = basename + '*'
        
        return basename

    @property
    def filename(self):
        return self._filename
    
    @filename.setter
    def filename(self, newname):
        self._filename = newname
        
        # empty watcher (it should contain only the current file)
        # and fill with current file
        files = self.fileWatcher.files()
        if len(files) > 0:
            self.fileWatcher.removePaths(self.fileWatcher.files())
            
        directories = self.fileWatcher.directories()
        if len(directories) > 0:
            self.fileWatcher.removePaths(self.fileWatcher.directories())
            
        self.fileWatcher.addPath(newname)

    @property
    def folder(self):
        return self._folder

    def on_fileChanged(self, filename):
        """
        reload when disk file is changed
        """
        x, y = self.getCursorPosition()
        self.openFile(filename)
        self.setCursorPosition(x,y)

    # 
    # Define behavior
    #
        
    def on_textChanged(self, changed=True):
 
        # If the text is changed, reset the search
        self._unsearched = True
        status_changed = changed != self._changed

        if status_changed:

            self._changed = changed
            
            self.setParentTitle(self.name)
            
    def setText(self, text, *args, **kwargs):
        super(SimplePythonEditorTextField, self).setText(text, *args, **kwargs)
        
        # Convert EOL chars        
        self.convertEols(self.eolMode())        
        self._changed = True
        self.on_textChanged(False)

    def openFile(self, filename):
        try:
            with open(filename, 'r') as f:
                text = f.read()
        except:
            pass
        else:
            self.filename = filename
            self._folder = os.path.dirname(filename)
            self.setText(text)
            
    def saveFile(self, filename):

        # Write file
        self.fileWatcher.blockSignals(True)
        with open(filename, 'w') as f:
            f.write(self.text())
        self.fileWatcher.blockSignals(False)

        self._folder = os.path.dirname(filename)
        self.filename = filename
        self.on_textChanged(False)


    def on_save(self, checked=True):
        
        # Ignore if no file selected
        if not self.filename:
            return

        # save file
        self.saveFile(self.filename)

    def on_save_as(self, checked=True):
        filename = QtGui.QFileDialog.getSaveFileName(self,
                                                     'Select python file',
                                                     self._folder,
                                                     "Python files (*.py)")
        if not filename:
            # User cancelled selection
            return
            
        # Convert to standard platform specific path, otherwise Qt likes forward slashes:
        current_filename = os.path.abspath(filename)

        # save current file
        self.saveFile(current_filename)

    def on_open_named(self, filename=''):
        if not filename:
            return
            
        # Convert to standard platform specific path, otherwise Qt likes forward slashes:
        current_filename = os.path.abspath(filename)

        # save current file
        self.openFile(current_filename)

    def restart_find_replace(self):
        self._unsearched = True

    def do_find_next(self, text, case_sensitive=False, whole_word=False, wrap_search=False, forward=True):

        if self._unsearched or not forward:
            line_from, index_from, _line_to, _index_to = self.getSelection()
            self.setCursorPosition(line_from, max([0, index_from-1]))


        if self._unsearched:
            found = self.findFirst(text, 
                                      False,
                                      case_sensitive,
                                      whole_word, 
                                      wrap_search,
                                      forward=forward, 
                                      line=-1,
                                      index=-1,
                                      show=True,
                                      posix=False)
            if found:
                self._unsearched = False
        else:
            found = self.findNext()
                    
        return found

    def on_find_replace(self, text,
                        replace_text='',
                        replace=False, 
                        replace_all=False, 
                        **kwargs):
        if text:
            if replace:
                while True:
                    self.replace(replace_text)
                    found = self.do_find_next()

                    if not found or not replace_all:
                        break
            else:
                self.do_find_next(text, **kwargs)

    