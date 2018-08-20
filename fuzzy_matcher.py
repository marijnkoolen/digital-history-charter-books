import re

class FuzzyMatcher(object):
    
    def __init__(self, char_match_threshold=0.5, ngram_threshold=0.5, levenshtein_threshold=0.5, max_length_variance=1):
        self.char_match_threshold = char_match_threshold
        self.ngram_threshold = ngram_threshold
        self.levenshtein_threshold = levenshtein_threshold
        self.perform_strip_suffix = True
        self.max_length_variance = max_length_variance

    def enable_strip_suffix(self):
        self.perform_strip_suffix = True
        
    def disable_strip_suffix(self):
        self.perform_strip_suffix = False
        
    #################################
    # String manipulation functions #
    #################################

    def make_ngrams(self, term, n):
        term = "#{t}#".format(t=term)
        max_start = len(term) - n + 1
        return [term[start:start+n] for start in range(0, max_start)]

    def strip_suffix(self, match):
        if match[-2] in [" ", ","]:
            match = match[:-2]
        elif match[-2:] in [", ", ". ", "? ", ".f"]:
            match = match[:-2]
        elif match[-1] in [" ", ",", "."]:
            match = match[:-1]
        return match

    #####################################
    # Term similarity scoring functions #
    #####################################

    def score_levenshtein_distance(self, s1, s2):
        if len(s1) > len(s2):
            s1, s2 = s2, s1
        distances = range(len(s1) + 1)
        for i2, c2 in enumerate(s2):
            distances_ = [i2+1]
            for i1, c1 in enumerate(s1):
                if c1 == c2:
                    distances_.append(distances[i1])
                else:
                    distances_.append(1 + min((distances[i1], distances[i1 + 1], distances_[-1])))
            distances = distances_
        return distances[-1]

    def score_char_overlap(self, term1, term2):
        num_char_matches = 0
        for char in term2:
            if char in term1:
                term1 = term1.replace(char, "", 1)
                num_char_matches += 1
        return num_char_matches

    def score_ngram_overlap(self, term1, term2, ngram_size):
        term1_ngrams = self.make_ngrams(term1, ngram_size)
        term2_ngrams = self.make_ngrams(term2, ngram_size)
        overlap = 0
        for ngram in term1_ngrams:
            if ngram in term2_ngrams:
                term2_ngrams.pop(term2_ngrams.index(ngram))
                overlap += 1
        return overlap

    def score_char_overlap_ratio(self, term1, term2):
        max_overlap = len(term1)
        overlap = self.score_char_overlap(term1, term2)
        return overlap / max_overlap

    def score_ngram_overlap_ratio(self, term1, term2, ngram_size):
        max_overlap = len(self.make_ngrams(term1, ngram_size))
        overlap = self.score_ngram_overlap(term1, term2, ngram_size)
        return overlap / max_overlap

    def score_levenshtein_distance_ratio(self, term1, term2):
        max_distance = max(len(term1), len(term2))
        distance = self.score_levenshtein_distance(term1, term2)
        return 1 - distance / max_distance

    #################################
    # Candidate filtering functions #
    #################################

    def filter_char_match_candidates(self, candidates, match_term):
        if len(candidates) == 0:
            return candidates
        if isinstance(candidates[0], str):
            return [candidate for candidate in candidates if self.score_char_overlap_ratio(candidate, match_term) >= self.char_match_threshold]
        elif isinstance(candidates[0], object):
            return [candidate for candidate in candidates if self.score_char_overlap_ratio(candidate["match_string"], match_term) >= self.char_match_threshold]

    def filter_ngram_candidates(self, candidates, match_term, ngram_size):
        if len(candidates) == 0:
            return candidates
        if isinstance(candidates[0], str):
            return [candidate for candidate in candidates if self.score_ngram_overlap_ratio(candidate, match_term, ngram_size) >= self.ngram_threshold]
        elif isinstance(candidates[0], object):
            return [candidate for candidate in candidates if self.score_ngram_overlap_ratio(candidate["match_string"], match_term, ngram_size) >= self.ngram_threshold]

    def filter_levenshtein_candidates(self, candidates, match_term):
        if len(candidates) == 0:
            return candidates
        if isinstance(candidates[0], str):
            return [candidate for candidate in candidates if self.score_levenshtein_distance_ratio(candidate, match_term) >= self.levenshtein_threshold]
        elif isinstance(candidates[0], object):
            return [candidate for candidate in candidates if self.score_levenshtein_distance_ratio(candidate["match_string"], match_term) >= self.levenshtein_threshold]

    def filter_candidates(self, candidates, keyword, ngram_size=2):
        if len(candidates) == 0:
            return candidates
        char_match_candidates = self.filter_char_match_candidates(candidates, keyword)
        ngram_candidates = self.filter_ngram_candidates(char_match_candidates, keyword, ngram_size)
        return self.filter_levenshtein_candidates(ngram_candidates, keyword)

    def rank_candidates(self, candidates, keyword, ngram_size=2):
        total_scores = []
        for candidate in candidates:
            if isinstance(candidate, str):
                match_string = candidate
            elif isinstance(candidate, object):
                match_string = candidate["match_string"]
            score = {
                "candidate": candidate,
                "char": self.score_char_overlap_ratio(match_string, keyword),
                "ngram": self.score_ngram_overlap_ratio(match_string, keyword, ngram_size),
                "levenshtein": self.score_levenshtein_distance_ratio(match_string, keyword),
            }
            score["total"] = score["char"] + score["ngram"] + score["levenshtein"]
            total_scores += [score]
        return sorted(total_scores, key=lambda x: x["total"], reverse=True)

    ##########################################
    # Functions for finding patterns in text #
    ##########################################

    def find_term_matches(self, text, term, max_length_variance=None):
        if not max_length_variance:
            max_length_variance = self.max_length_variance
        initial = term[0]
        length_range = {"min": len(term[1:]) - max_length_variance, "max": len(term[1:]) + max_length_variance}
        if initial in ["[","]", "*", "(",")", "."]:
            initial = "\\" + initial
        pattern = initial + ".{" + str(length_range["min"]) + "," + str(length_range["max"]) + "}"
        try:
            return [create_term_match(re_match, term) for re_match in re.finditer(pattern, text)]
        except TypeError:
            print("\n\nERROR\n\n")
            print("text:", text)
            print("term:", term)
            print("pattern:", pattern)
            raise

    def find_start_candidates(self, paragraph, term):
        candidates = []
        for match in self.find_term_matches(paragraph, term):
            if self.perform_strip_suffix:
                match["match_string"] = self.strip_suffix(match["match_string"])
            candidates.append(match)
        return candidates

    def find_candidates(self, text, keyword, ngram_size=2):
        candidates = self.find_start_candidates(text, keyword)
        candidates = self.filter_char_match_candidates(candidates, keyword)
        candidates = self.filter_ngram_candidates(candidates, keyword, ngram_size)
        candidates = self.filter_levenshtein_candidates(candidates, keyword)
        return candidates
        

def create_term_match(re_match, term):
    return {
        "match_term": term,
        "match_string": re_match.group(0),
        "match_offset": re_match.start()
    }




