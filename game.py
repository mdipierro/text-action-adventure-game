import re
import sys
import cPickle
import readline; readline.parse_and_bind("tab: complete")


OPPOSITES = {'visible':'invisible',
             'invisible':'visible',
             'locked':'unlocked',
             'unlocked':'locked'}

PLURAL = 'plural'
LOCKED = 'locked'
INVISIBLE = 'invisible'
WINNER = 'winner'

YOU = 'you'
_AND_ = ' and '

NAME, ARTICLE, HAS, IS, IN, ON, UNDER, NEAR, ATTR, EVENTS, SAYS, TO, CAN = \
    'name|article|has|is|in|on|under|near|attr|events|says|to|can'.split('|')

ARTICLES = 'a|an|the|this|that|mine|your|his|her|its|their'.split('|')
PREPOSITIONS = 'in|on|under|near'.split('|')

RE_CLEAN       = re.compile('\s+')
RE_PUNCTUATION = re.compile('\s*([., ;:])\s*$')
RE_IF          = re.compile('if (?P<c>.*?) then (?P<a>.*)$')
RE_CONFIG = [
    (re.compile('(?P<s>.+?) says "(?P<o>.+)"$'),                                  SAYS),
    (re.compile('(the )?(?P<k>.+?) of (?P<s>.+?) (is|are|becomes?) (?P<v>.+)$'),  ATTR),
    (re.compile('(?P<s>.+?) (is|are|moves?) in (?P<o>.+)$'),                      IN),
    (re.compile('(?P<s>.+?) (is|are|moves?) on (?P<o>.+)$'),                      ON),
    (re.compile('(?P<s>.+?) (is|are|moves?) near (?P<o>.+)$'),                    NEAR),
    (re.compile('(?P<s>.+?) (is|are|moves?) under (?P<o>.+)$'),                   UNDER),
    (re.compile('(?P<s>.+?) (is|are|becomes?) (?P<o>.+)$'),                       IS),
    (re.compile('(?P<s>.+?) can (?P<v>\w+) (?P<o>.+)$'),                          CAN),
    (re.compile('(?P<s>.+?) (has|have) (?P<o>.+)$'),                              HAS),
    (re.compile('(?P<s>.+?) leads to (?P<o>.+?)$'),                               TO),
]

CONDITION, ACTION, SUBJECT, OBJECT, KEY, VALUE, VERB = 'c|a|s|o|k|v|v'.split('|')

RE_INPUT = [
    (re.compile('internals'),                            'internals'),
    (re.compile('(\?|help)'),                            'help'),
    (re.compile('where am I[\?]?'),                      'where_am_i'),
    (re.compile('who am I[\?]?'),                        'who_am_i'),
    (re.compile('what do I (have|carry)[\?]?'),          'what_do_i_have'),
    (re.compile('look around'),                          'look_around'),
    (re.compile('look at (?P<name>.*)'),                 'look_at'),
    (re.compile('(enter|go to|move to) (?P<name>.*)'),   'enter'),
    (re.compile('save game to (?P<filename>[\w\.]+)'),   'save'),
    (re.compile('load game from (?P<filename>[\w\.]+)'), 'load'),
    (re.compile('take (?P<name>.*)'),                    'take'),
    (re.compile('drop (?P<name>.*)'),                    'drop'),
    (re.compile('(?P<verb>[\w\-]+) (?P<name>.*)'),       'action'),
    ]

MSG_WIN = 'won the game'
MSG_YOU_ARE = 'you are %s'
MSG_YOU_ARE_IN = 'you are in %s'
MSG_YOU_HAVE = 'you have %s'
MSG_YOU_SEE = 'you see %s'
MSG_DONT_UNDERSTAND = 'sorry, I do not understand'
MSG_NOTHING_HAPPENED = 'nothing happened'
MSG_NOT_ALLOWED = 'not allowed'
MSG_YOU_CANNOT = 'you cannot %s'
MSG_SAVED = 'game saved'
MSG_LOADED = 'game loaded'
MSG_TAKEN = '%s taken'
MSG_DROPPED = '%s dropped'
MSG_ENTERED = 'you entered %s'
MSG_UNKNOWN = "%s is unknown"
MSG_NOT_PLACE = "%s is not a place"
MSG_INSIDE_ALREADY = 'you are in %s already'
MSG_UNKNOWN_WAY = "no known way to get to %s"
MSG_UNKOWN = 'unknown'
MSG_THING_UNKNOWN = '%s unknown'
MSG_CANNOT_TAKE_SELF = 'you cannot lift yourself!'

HELP = """
Commands:
- ?
- help
- who am I?
- what am I?
- what do I have?
- look aroung
- look at <thing>
- take <thing>
- drop <thing>
- enter <thing>
- <verb> <thing>
- internals
"""

class Message(RuntimeError): pass

def normalize(text):
    text = RE_CLEAN.sub(' ', text.strip())
    text = RE_PUNCTUATION.sub('\g<1> ', text).strip()
    return text

def article_split(subj):
    """
    breaks subj=='the green cat' into ('the', 'green cat')
    """
    parts = subj.split(' ', 1)
    article = parts[0].lower()
    if len(parts)>1 and article in ARTICLES:
        article = article+' '
        parts = parts[1:]
    else:
        article = ''
    return article, ' '.join(parts).lower()

def add_opposites(s, noun):
    """
    deal with the fact that a thing cannot be
    visible and invisible or locked and unlocked at the same time
    """
    s.add(noun)
    opposite = OPPOSITES.get(noun)
    if opposite and opposite in s:
        s.remove(opposite)
        
def find_match(text, cases):
    for regex, verb in cases:
        match = regex.match(text)
        if match:
            return verb, match.groupdict()
    return None, None

class Event(object):
    """
    this class is used to store game events: if {conditions} then {effects}
    """
    def __init__(self, things, conditions, effects):
        self.things = things
        self.conditions = conditions
        self.effects = effects

    def __call__(self):
        condition = True
        for verb, groupdict in self.conditions:
            article, key = article_split(groupdict[SUBJECT])
            thing = self.things.get(key)
            if not thing:
                condition = False
            else:
                values = thing[verb]
                if isinstance(values, set):
                    article, key = article_split(groupdict[OBJECT])
                    if not key in values:
                        condition = False
                elif isinstance(values, dict):
                    if values[groupdict[KEY]] != groupdict[VALUE]:
                        condition = False
                else:
                    condition = False
        if not condition:
            return MSG_NOTHING_HAPPENED
        messages = []
        for verb, groupdict in self.effects:
            article, key = article_split(groupdict[SUBJECT])
            thing = self.things.get(key)
            if not thing:
                return MSG_NOTHING_HAPPENED
            values = thing[verb]
            if verb == SAYS:
                thing[verb] = groupdict[OBJECT]
                messages.append('%(s)s says "%(o)s"' % groupdict)
            elif isinstance(values, set):
                article, key = article_split(groupdict[OBJECT])
                add_opposites(values, key)
                groupdict['verb'] = verb
                messages.append('%(s)s %(verb)s %(o)s' % groupdict)
            elif isinstance(values, dict):
                thing[verb][groupdict[KEY]] = groupdict[VALUE]
                messages.append('%(k)s of %(s)s is %(v)s' % groupdict)
        return '\n'.join(messages) or MSG_NOTHING_HAPPENED
    def __repr__(self):
        return 'event(%s conditions->%s effects)' % (len(self.conditions), len(self.effects))

class Parser(object):
    def __init__(self, input):
        """
        input the game script, see sample below
        """
        self.things = {}
        self.get_or_store_thing(YOU)
        for k, rawline in enumerate(input.split('\n')):
            line = normalize(rawline)
            if line and not line.startswith('#'):
                if not self.parse_statement(line):
                    raise RuntimeError('Error parsing line %s: %s' % (k, rawline))

    def get_or_store_thing(self, subj):
        """
        if there is no object called subj, it will create one in self.things
        else it will return it. each self.things[subj] is a dict like:

        {NAME:key, ARTICLE:article, SAYS:None, EVENTS:{},
         ATTR:{}, IS:set(), HAS:set(), TO:set(),
         IN:set(), ON:set(), UNDER:set(), NEAR:set()}

         for example

        {NAME:'cat', ARTICLE:'the', SAYS:'hello!', EVENTS:{},
         ATTR:{'color':'red'}, IS:set(['invisible']),
         HAS:set(['collar', 'food']), TO:set(),
         IN:set(['box']), ON:set(['table']),
         UNDER:set(['roof']), NEAR:set(['fireplace'])}

        """
        article, key = article_split(subj)
        if not key in self.things:
            self.things[key] = {
                NAME:key, ARTICLE:article, SAYS:None, EVENTS:{},
                ATTR:{}, IS:set(), HAS:set(), TO:set(),
                IN:set(), ON:set(), UNDER:set(), NEAR:set()}
        return self.things[key]

    def parse_statement(self, statement):
        """
        parse a statement from the input file a self.things or attribute
        """
        # code to handle events
        m = RE_IF.match(statement)
        if m:
            cond = m.group(CONDITION).replace(', ', _AND_).split(_AND_)
            actions = m.group(ACTION).replace(', ', _AND_).split(_AND_)
            if not cond[0].startswith(YOU+' '):
                return False
            cause, name = cond[0][4:].split(' ', 1)
            article, key = article_split(name)
            thing = self.get_or_store_thing(key)
            conditions = []
            for other_conditions in cond[1:]:
                verb, match = find_match(other_conditions, RE_CONFIG)
                if match:
                    conditions.append((verb, match))
            effects = []
            for action in actions:
                verb, match = find_match(action, RE_CONFIG)
                if not match:
                    return False
                if OBJECT in match:
                    self.get_or_store_thing(match[OBJECT])
                effects.append((verb, match))
            events = thing[EVENTS][cause] = thing[EVENTS].get(cause, set())
            events.add(Event(self.things, conditions, effects))
            return True
        # code to handle status
        verb, match = find_match(statement, RE_CONFIG)
        if not match:
            return False
        thing = self.get_or_store_thing(match[SUBJECT])
        if verb == ATTR:
            thing[ATTR][match[KEY]] = match[VALUE]
        elif verb == CAN:
            if thing[NAME] != YOU:
                return False
            obj = self.get_or_store_thing(match[OBJECT])
            obj[EVENTS][match[VERB]] = set()
        else:
            if verb == SAYS:
                thing[verb] = match[OBJECT]
            else:
                other = self.get_or_store_thing(match[OBJECT])
                thing[verb].add(other[NAME])
                if verb == TO:
                    other[IS].add('place')
        return True

class Game(object):

    def __init__(self, input):
        self.things = Parser(input).things

    def pretty_print(self):
        text = ''
        for key in sorted(self.things):
            thing = self.things[key]
            text += '%s\n' % thing[NAME]
            for key, value in thing.items():
                if value:
                    text += '  - %s: %s\n' % (key, value)
        return text

    def enter_place(self, fullname, force=False):
        """
        for example game.enter_place('the bedroom')
        on success returns the message associated to the new place
        on error raises an exception
        """
        article, name = article_split(fullname)
        if not name in self.things:
            raise Message(MSG_UNKNOWN % fullname)
        thing = self.things[name]
        if not 'place' in thing[IS]:
            raise Message(MSG_NOT_PLACE % fullname)
        you = self.things[YOU]
        if name in you[IN]:
            raise Message(MSG_INSIDE_ALREADY % fullname)
        things = [self.things[key] for key in self.visible()]
        places = reduce(lambda a, b:a|b,
                        [thing[TO] for thing in things if
                         not LOCKED in thing[IS]], set())
        if force or name in places:
            self.things[YOU][IN] = set([name])
            message = self.things[name][SAYS] or ''
            if MSG_WIN in message:
                self.things[YOU][IS].add(WINNER)
            return message
        raise Message(MSG_UNKNOWN_WAY % fullname)

    def can_see(self, name, taken=True):
        """
        game.can_see('the cat') -> True or False
        """
        thing = self.things.get(name)
        if not thing:
            raise Message(MSG_THING_UNKNOWN % name)
        you = self.things[YOU]
        if taken and thing[NAME] in you[HAS]:
            return True
        if INVISIBLE in thing[IS]:
            return False
        return (name in you[IN] or you[IN].intersection(thing[IN]))

    def visible(self):
        """
        returns a list of names of visible things
        """
        return [name for name in self.things if self.can_see(name, taken=False)]

    def join(self, items):
        """
        joins the list of items after adding articles
        """
        return ', '.join('%(article)s%(name)s' % self.things[item] for item in items)

    def take_thing(self, name):
        """
        take a thing by adding to self.things[YOU][HAS]
        """
        article, name = article_split(name)
        if name == YOU:
            raise Message(MSG_CANNOT_TAKE_SELF)
        you = self.things[YOU]
        if self.can_see(name):
            thing = self.things[name]
            for k in PREPOSITIONS:
                thing[k].clear()
            you[HAS].add(name)
        else:
            raise Message(MSG_THING_UNKNOWN % name)

    def drop_thing(self, name):
        """
        drop something you have in the your currently are
        """
        article, name = article_split(name)
        you = self.things[YOU]
        if name in you[HAS]:
            thing = self.things[name]
            thing[IN] |= you[IN]
            you[HAS].remove(name)
        else:
            raise Message("you do not have %s" % name)

    def inspect(self, name):
        """
        returns a string with the description of thing name
        """
        article, name = article_split(name)
        if self.can_see(name):
            thing = self.things[name]
            you = self.things[YOU]
            s = ''
            fullname = '%s%s' % (article, name)
            v = 'are' if name == YOU or 'plural' in thing[IS] else IS
            if thing[IS]:
                s += '%s %s %s\n' %(fullname, v, self.join(thing[IS]))
                if thing[IN] - you[IN]:
                    s += '%s %s in %s\n' %(fullname, v, self.join(thing[IN]-you[IN]))
            if thing[ON]:
                s += '%s %s on %s\n' %(fullname, v, self.join(thing[ON]))
            if thing[UNDER]:
                s += '%s %s under %s\n' %(fullname, v, self.join(thing[UNDER]))
            if thing[NEAR]:
                s += '%s %s near %s\n' %(fullname, v, self.join(thing[NEAR]))
            for key, value in thing[ATTR].items():
                s += 'the %s of %s is %s\n' %(key, fullname, value)
            v = 'have' if name == YOU or 'plural' in thing[IS] else HAS
            if thing[HAS]:
                s += '%s %s %s\n' %(fullname, v, self.join(thing[HAS]))
            if thing[EVENTS]:
                s += 'you can %s %s\n' % (
                    ', '.join(thing[EVENTS].keys()), fullname)
            if thing[TO]:
                s += 'it leads to %s\n' % (', '.join(thing[TO]))
            return s
        else:
            raise Message(MSG_THING_UNKNOWN % name)

    #### methods that perform I for user interface

    def where_am_i(self):
        return MSG_YOU_ARE_IN % ', '.join(self.things[YOU][IN])

    def who_am_i(self):
        if self.things[YOU][IS]:
            return MSG_YOU_ARE % ', '.join(self.things[YOU][IS])
        else:
            return MSG_UNKOWN

    def what_do_i_have(self):
        if self.things[YOU][HAS]:
            return MSG_YOU_HAVE % ', '.join('%(article)s%(name)s' % self.things[key]
                                            for key in self.things[YOU][HAS])
        else:
            return MSG_UNKOWN

    def look_around(self):
        names = self.visible()
        return MSG_YOU_SEE % ', '.join('%(article)s%(name)s' % self.things[key]
                                       for key in names if not key == YOU)

    def look_at(self, name):
        return self.inspect(name).rstrip()

    def enter(self, name):
        message = self.enter_place(name)
        return (MSG_ENTERED % name) +'\n' + message

    def internals(self):
        return self.pretty_print()

    def help(self):
        return HELP

    def save(self, filename):
        cPickle.dump(self.things, open(filename, 'wb'))
        return MSG_SAVED

    def load(self, filename):
        self.things = cPickle.load(open(filename, 'rb'))
        return MSG_SAVED

    def take(self, name):
        self.take_thing(name)
        return MSG_TAKEN % name

    def drop(self, name):
        self.drop_thing(name)
        return MSG_DROPPED % name

    def action(self, verb, name):
        article, key = article_split(name)
        if self.can_see(key,taken=True):
            thing = self.things[key]
            if not verb in thing[EVENTS]:
                raise Message(MSG_YOU_CANNOT % ('%s %s' % (verb, name)))
            messages = []
            for event in thing[EVENTS].get(verb, set()):
                messages.append(event())
            return '\n'.join(messages) or MSG_NOTHING_HAPPENED        
        return MSG_NOT_ALLOWED

    def start(self):
        for place in self.things[YOU][IN]:
            message = self.things[place][SAYS]
            if message:
                print message

    def run(self, func_name, match):
        try:
            message = getattr(self, func_name)(**match) if func_name else MSG_DONT_UNDERSTAND
        except Message, e:
            message = str(e)
        print message
        return 'winner' in self.things[YOU][IS]

    def input(self, echo=False):
        command = raw_input('YOU> ')
        if echo:
            print command
        return command

    def loop(self, echo=False):
        self.start()
        while True:
            command = self.input(echo)
            command = normalize(command)
            func_name, match = find_match(command, RE_INPUT)
            if self.run(func_name, match):
                return # end of game!

    def play(self, echo=False):
        try:
            self.loop(echo=echo)
        except (EOFError, KeyboardInterrupt):
            print

SAMPLE="""
you are in the bedroom
the bedroom says "the scope of the game is to get to the bathroom"
a green door is in the bedroom
the green door is locked
the green door leads to the bathroom
a cat is in the bedroom
the color of the cat is white
a table is in the bedroom
the cat is on the table
a blue key is in the bedroom
the blue key is under the table
the blue key is invisible
the cat is meowing
you can kick the table
if you poke the cat then the cat says "kick the table"
if you kick the table then the blue key is visible
if you use the blue key and you have the blue key then the green door is unlocked
the bathroom says "you made it here and won the game!"
"""

if __name__ == '__main__':
    input = open(sys.argv[1]).read() if len(sys.argv)>1 else SAMPLE
    echo = len(sys.argv)>2 and sys.argv[2]=='echo'
    Game(input).play(echo=echo)
