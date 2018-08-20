# Created by: Marijn Koolen
# Created on: 2018-08-13
# Context: parsing digitized charter books to extract geographic attestations and dates


import re
from bs4 import BeautifulSoup as bsoup


class HOCRPage(object):
    
    def __init__(self, hocr_page_soup, page_num=None, minimum_paragraph_gap=10, avg_char_width=20):
        """
        Action: parses a hOCR page document based on HTML parser Beautiful Soup
        Input: a Beautiful Soup object of the hOCR page
        Output: a HOCRPAGE object with paragraphs, lines and words and their page positions
                as well as a representation of the lines with whitespace restored based on
                word positioning.
        
        Three optional input arguments:
        
        1. page_num: set a page number for this page
        
        2. minimum_paragraph_gap: is used to estimate line skips between paragraphs 
        as boundaries. Default value is based on OHZ charter books, for others
        it's possibly higher or lower.
        
        3. avg_char_width: is used to estimate width of whitespaces between words
        default value is based on averaging over pixel width and character 
        length of recognised words in OHZ charter books.
        
        """
        self.tag = hocr_page_soup.name
        self.page_num = page_num
        self.class_ = hocr_page_soup['class']
        self.attributes = get_hocr_title_attributes(hocr_page_soup)
        self.box = get_hocr_box(hocr_page_soup)
        self.lines = []
        self.paragraphs = []
        self.minimum_paragraph_gap = minimum_paragraph_gap
        self.avg_char_width = avg_char_width 

        
    def set_carea(self, hocr_page_soup):
        hocr_carea_soup = get_hocr_carea_soup(hocr_page_soup)
        self.carea = get_hocr_box(hocr_carea_soup)
        
    def set_paragraphs(self):
        paragraph = make_empty_paragraph()
        for line_number, line in enumerate(self.lines):
            if "clean_line_text" in line:
                paragraph["line_texts"].append(line["clean_line_text"])
            else:
                paragraph["line_texts"].append(line["spaced_line_text"])
            paragraph["line_numbers"].append(line_number)
            paragraph["page_num"] = self.page_num
            paragraph["paragraph_num"] = len(self.paragraphs)
            if line_number < len(self.lines) - 1:
                gap_to_next = int(self.lines[line_number+1]["bbox"][1] - line["bbox"][3])
                if gap_to_next > self.minimum_paragraph_gap:
                    self.paragraphs.append(paragraph)
                    paragraph = make_empty_paragraph()
        self.paragraphs.append(paragraph)
        
    def merge_paragraph_lines(self):
        for paragraph in self.paragraphs:
            text = ""
            for line in paragraph["line_texts"]:
                if len(line) == 0:
                    continue
                if line[-1] == "-":
                    # Crude but quick. TODO more proper line break hyphenation analysis
                    text += line[:-1].strip()
                else:
                    text += line.strip() + " "
            paragraph["merged_text"] = text
                
        
    def within_range(self, line_index):
        # mostly, line numbers at every 5 lines, i.e. 5, 10, 15, 20, 25, ...
        # sometimes there's a mistake, with line number one line early or late
        # e.g. OHZ part 1, page 6, line 40
        if line_index < 4:
            return None
        offset = line_index % 5
        if offset == 0:
            return line_index
        elif offset == 1:
            return line_index - 1
        elif offset == 4:
            return line_index + 1
        else:
            return None
        
    def is_even_side(self):
        if self.page_num % 2 == 0:
            return True
        else:
            return False
        
    def close_to_carea_edge(self, line_index):
        # Determine if a line has text close to the left/right margin.
        # This is used for a.o. determining whether there is a line number in the line text.
        if self.is_even_side():
            # for even numbered pages look at distance to right edge of text area
            distance_from_margin = self.carea["right"] - self.lines[line_index]["right"]
        else: 
            # for uneven numbered pages look at distance to left edge of text area
            distance_from_margin =  self.lines[line_index]["left"] - self.carea["left"]
        # From eyeballing and testing, line numbers are no more than distance 70 from margin
        return True if distance_from_margin < 70 else False
        
    def sticks_out(self, line_index):
        # Lines with a line number stick out from their surrounding lines. 
        # Some testing suggests line number 5 always sticks out at least 30 from surrounding lines
        # Higher (double digit) line unmbers sticks out at least 40.
        # This occasionally doesn't work...
        if line_index < 4: # ignore first few lines
            return None
        min_stick_out = 40
        if line_index < 7:
            min_stick_out = 30
        surrounding_lines =  self.lines[line_index-2:line_index] + self.lines[line_index+1:line_index+3]
        for neighbour_line in surrounding_lines:
            if self.is_even_side():
                if self.lines[line_index]["right"] - neighbour_line["right"] < min_stick_out:
                    return False
            else:
                if neighbour_line["left"] - self.lines[line_index]["left"] < min_stick_out:
                    return False
        return True
        
    def has_line_number(self, line_index, line_number):
        # check if line text contains a line number:
        if self.is_even_side():
            stick_out_word = self.lines[line_index]["words"][-1]["word_text"]
        else:
            stick_out_word = self.lines[line_index]["words"][0]["word_text"]
        if self.looks_like_line_number(stick_out_word, line_number):
            return True
        else:
            return False
        
    def looks_like_line_number(self, word, line_number):
        if line_number % 10 == 0: # confusion of digit 0
            word = re.sub("[oO]$", "0", word)
        elif line_number % 10 == 5: # confusion of digit 5
            word = re.sub("[sS]$", "5", word)
        if line_number in [10, 15]: # confusion of digit 1
            word = re.sub("^[iIr]", "1", word)
        if str(line_number) == word:
            return True
        else:
            return False
    
    def remove_line_numbers(self):
        for line_index, line in enumerate(self.lines):
            line["clean_line_text"] = self.remove_line_number(line_index)
            if not line["clean_line_text"]:
                line["clean_line_text"] = ""
    
    def remove_line_number(self, line_index):
        # Remove line numbers so that lines with line break hyphens
        # can be properly merged with next lines.
        # 1 line text should run close to margin
        # 2 line text should stick out from surrounding lines
        # 3 line text should have something that looks like a number at start/end of line
        # Sloppy implementation, should just check
        # every fifth line first for number equal to index+1
        line_number = self.within_range(line_index)
        if not line_number:
            return self.lines[line_index]["spaced_line_text"]
        if not self.close_to_carea_edge(line_index):
            return self.lines[line_index]["spaced_line_text"]
        if not self.sticks_out(line_index):
            return self.lines[line_index]["spaced_line_text"]
        if self.has_line_number(line_index, line_number):
            if self.is_even_side():
                return self.get_spaced_line_text(self.lines[line_index]["words"][:-1])
            else:
                return self.get_spaced_line_text(self.lines[line_index]["words"][1:])
        else:
            return self.lines[line_index]["spaced_line_text"]
            
        
    def set_lines(self, hocr_page_soup):
        # store all lines separately as:
        # line_text:        simple text representation
        # spaced_line_text: whitespace maintained representation (for indentation, column spacing, margins, ...)
        # words:            keep individual words and their coordinates
        for hocr_line_soup in get_hocr_lines(hocr_page_soup):
            line = get_hocr_box(hocr_line_soup)
            line["line_text"] = hocr_line_soup.get_text()
            line["words"] = get_words(hocr_line_soup)
            line["spaced_line_text"] = self.get_spaced_line_text(line["words"])
            # occasionally, lines only contain a pipe char based on edge shading in scan
            # skip those lines. 
            if line["line_text"].strip() == "|" or line["line_text"].strip() == "|" or len(line["line_text"]) == 1:
                continue
            self.lines.append(line)

    def get_spaced_line_text(self, words):
        # use word coordinates to reconstruct spacing between words
        spaced_line_text = ""
        if len(words) == 0:
            return spaced_line_text
        offset = words[0]["bbox"][0] - self.carea["left"]
        spaced_line_text = " " * int(round(offset / self.avg_char_width))
        for index, word in enumerate(words[:-1]):
            spaced_line_text += word["word_text"]
            spaced_line_text += self.get_spaces(word, words[index+1])
        spaced_line_text += words[-1]["word_text"]
        return spaced_line_text
    
    def get_spaces(self, word1, word2):
        # Simple computation based on word coordinates to determine
        # white spacing between them.
        space_to_next = word2["left"] - word1["right"]
        spaces = int(round(space_to_next / self.avg_char_width))
        if spaces == 0:
            spaces = 1
        return " " * spaces



def make_empty_paragraph():
    return {
        "type": None,
        "line_texts": [],
        "line_numbers": [],
    }
        
def get_hocr_box(hocr_soup):
    # extract hocr bounding box, compute size and explicate offsets
    element_bbox = get_hocr_bbox(hocr_soup)
    box_size = get_bbox_size(element_bbox)
    return {
        "bbox": element_bbox,
        "width": box_size[0],
        "height": box_size[1],
        "left": element_bbox[0],
        "right": element_bbox[2],
        "top": element_bbox[1],
        "bottom": element_bbox[3]
    }

def get_hocr_content(hocr_file):
    with open(hocr_file, 'rt') as fh:
        return bsoup(fh, 'lxml')
        
def get_hocr_page_soup(hocr_soup):
    return hocr_soup.find("div", class_="ocr_page")

def get_hocr_carea_soup(hocr_soup):
    return hocr_soup.find("div", class_="ocr_carea")

def get_hocr_pars(hocr_soup):
    return hocr_soup.find_all("p", class_="ocr_par")

def get_hocr_lines(hocr_soup):
    return hocr_soup.find_all("span", class_="ocr_line")

def get_hocr_words(hocr_soup):
    return hocr_soup.find_all("span", class_="ocrx_word")

def get_hocr_bbox(hocr_element):
    attributes = get_hocr_title_attributes(hocr_element)
    return [int(coord) for coord in attributes["bbox"].split(" ")]
        
def get_hocr_title_attributes(hocr_element):
    return {part.split(" ", 1)[0]: part.split(" ", 1)[1] for part in hocr_element['title'].split("; ")}

def get_bbox_size(hocr_bbox):
    return hocr_bbox[2] - hocr_bbox[0], hocr_bbox[3] - hocr_bbox[1]
    
def get_word_conf(hocr_word):
    if "ocrx_word" in hocr_word['class']:
        attributes = get_hocr_title_attributes(hocr_word)
        if "x_wconf" in attributes:
            return int(attributes["x_wconf"])
    return None

def get_words(hocr_line):
    return [get_word(hocr_word) for hocr_word in get_hocr_words(hocr_line)]

def get_word(hocr_word_soup):
    # Extract all word information, including bounding box and confidence
    word_bbox = get_hocr_bbox(hocr_word_soup)
    word = get_hocr_box(hocr_word_soup)
    word["word_text"] = hocr_word_soup.get_text()
    word["word_conf"] = get_word_conf(hocr_word_soup)
    bbox_size = get_bbox_size(word_bbox)
    return word

def make_hocr_page(filepath, page_num=None, remove_line_numbers=False, minimum_paragraph_gap=10, avg_char_width=20):
    """
    make_hocr_page takes as input a filepath to a hOCR file and generates various textual representations of
    the hOCR data. For explanation of the optional arguments, see the HOCRPAGE class above. 
    """
    hocr_soup = get_hocr_content(filepath)
    hocr_page_soup = get_hocr_page_soup(hocr_soup)
    hocr_page = HOCRPage(hocr_page_soup, page_num, minimum_paragraph_gap=minimum_paragraph_gap, avg_char_width=avg_char_width)
    hocr_page.set_carea(hocr_page_soup)
    hocr_page.set_lines(hocr_page_soup)
    if remove_line_numbers:
        hocr_page.remove_line_numbers()
    hocr_page.set_paragraphs()
    hocr_page.merge_paragraph_lines()
    return hocr_page

