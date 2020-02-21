# -*- coding: utf-8 -*-


class Error(Exception):
    """Base class for other exceptions"""
    pass


class ConceptIdError(Error):
    """Something went wrong while creating the id of the concept"""
    pass


class LanguageElementError(Error):

    def __init__(self, language):
        message = "\n" + language[1] + " this language cell contains ???"
        self.message = message
        super().__init__(message) #desplay language name causing error


class CellParsingError(Error):

    def __init__(self, cell, comment=""):
        message = "\n" + comment + cell + "\n caused an error in the parser"
        self.message = message
        super().__init__(message)


class CellError(Error):
    """base class for formatting errors inside an element"""

    def __init__(self, values, type):
        message = "Value '{}' caused a {} error".format(values, type)
        self.message = message
        super().__init__(message)


class LanguageCellError(CellError):

    def __init__(self, values, type="language"):

        super().__init__(values, type)


class FormCellError(CellError):
    # phonemic, phonetic usf.
    def __init__(self, values, type):
        super().__init__(values, type)


class CognateCellError(CellError):

    def __init__(self, values, type="cognate"):
        super().__init__(values, type)


class CellParsingError(CellError):

    def __init__(self, values, type="parsing"):
        super().__init__(values, type)


if __name__ == "__main__":
    pass
