import re
import sys
import cPickle

OPPOSITES = {'visible':'invisible',
             'invisible':'visible',
             'locked':'unlocked',
             'unlocked':'locked'}

RE_CLEAN       = re.compile('\s+')
RE_PUNCTUATION = re.compile('\s*([.,;:])\s*$')
REGEX = [
    ('says',  re.compile('(?P<s>.+?) says "(?P<o>.+)"$')),
    ('attr',  re.compile('(the )?(?P<k>.+?) of (?P<s>.+?) (is|are|becomes?) (?P<v>.+)$')),
    ('in',    re.compile('(?P<s>.+?) (is|are|moves?) in (?P<o>.+)$')),
    ('on',    re.compile('(?P<s>.+?) (is|are|moves?) on (?P<o>.+)$')),
    ('near',  re.compile('(?P<s>.+?) (is|are|moves?) near (?P<o>.+)$')),
    ('under', re.compile('(?P<s>.+?) (is|are|moves?) under (?P<o>.+)$')),
    ('is',    re.compile('(?P<s>.+?) (is|are|becomes?) (?P<o>.+)$')),
    ('can',   re.compile('(?P<s>.+?) can (?P<v>\w+) (?P<o>.+)$')),
    ('has',   re.compile('(?P<s>.+?) (has|have) (?P<o>.+)$')),
    ('to',    re.compile('(?P<s>.+?) leads to (?P<o>.+?)$')),
]
RE_IF          = re.compile('if (?P<c>.*?) then (?P<a>.*)$')
ARTICLES = 'a|an|the|this|that|mine|your|his|her|its|their'.split('|')
INPUT = [
    (re.compile('internals'),                            'internals'),
    (re.compile('help'),                                 'help'),
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
HELP = """
Commands:
- who am I?
- what am I?
- what do I have?
- look aroung
- look at <thing>
- take <thing>
- drop <thing>
- enter <thing>
- <verb> <thing>
"""

class Message(RuntimeError): pass

def split(subj):
    """
    breaks subj=='the green cat' into ('the', 'green cat')
    """
    parts = subj.split(' ',1)
    article = parts[0].lower()
    if len(parts)>1 and article in ARTICLES:
        article = article+' '
        parts = parts[1:]
    else:
        article = ''
    return article, ' '.join(parts).lower()

def add(s,o):
    """
    deal with the fact that a thing cannot be
    visible and invisible or locked and unlocked at the same time
    """
    s.add(o)
    if o in OPPOSITES:
        p = OPPOSITES[o]
        if p in s:
            s.remove(p)

class Event(object):
    """
    this class is used to store game events: if {cause} then {effect}
    """
    def __init__(self,things,cause,effect):
        self.things = things
        self.cause = cause
        self.effect = effect
    def __call__(self):
        condition = True
        for verb,groupdict in self.cause:
            article, key = split(groupdict['s'])
            thing = self.things.get(key,None)
            if not thing:
                contition = False
                break
            values = thing.get(verb)
            if isinstance(values,set):
                if not groupdict['o'] in values:
                    contition = False
                    break
            elif isinstance(value,dict):
                if not values[groupdict['k']] == groupdict['v']:
                    contition = False
                    break
            else:
                condition = False
                break
        if not condition:
            return "nothing happened"
        messages = []
        for verb,groupdict in self.effect:
            article, key = split(groupdict['s'])
            thing = self.things.get(key,None)            
            if not thing:
                return "nothing happened"            
            values = thing[verb]
            if verb == 'says':
                thing[verb] = groupdict['o']
                messages.append('%(s)s says "%(o)s"' % groupdict)
            elif isinstance(values,set):
                a,k = split(groupdict['o'])
                add(values,k)
                groupdict['verb'] = verb
                messages.append('%(s)s %(verb)s %(o)s' % groupdict)
            elif isinstance(value,dict):
                thing[verb][groupdict['k']] = groupdict['v']
                messages.append('%(k)s of %(s)s is %(v)s' % groupdict['k'])
        return '\n'.join(messages) or "nothing happened"

class Game(object):
    def __init__(self, input):
        """
        input the game script, see sample below
        """
        self.things = {}
        self.get_or_store_thing('you')
        for k,line in enumerate(input.split('\n')):
            line = RE_CLEAN.sub(' ',line).strip()
            line = RE_PUNCTUATION.sub('\g<1> ',line).strip()
            if line and not line.startswith('#'):
                if not self.parse_statement(line):
                    raise Message('Error parsing line: %s' % k)

    def get_or_store_thing(self,subj):
        """
        if there is no object called subj, it will create one in self.things
        else it will return it. each self.things[subj] is a dict like:

        {'name':key, 'article':article, 'says':None, 'events':{},
         'attr':{},'is':set(),'has':set(),'to':set(),
         'in':set(),'on':set(),'under':set(),'near':set()}

         for example

        {'name':'cat', 'article':'the', 'says':'hello!', 'events':{},
         'attr':{'color':'red'},'is':set(['invisible']),
         'has':set(['collar','food']),'to':set(),
         'in':set(['box']),'on':set(['table']),
         'under':set(['roof']),'near':set(['fireplace'])}

        """
        article, key = split(subj)
        if not key in self.things:
            self.things[key] = {
                'name':key, 'article':article, 'says':None, 'events':{},
                'attr':{},'is':set(),'has':set(),'to':set(),
                'in':set(),'on':set(),'under':set(),'near':set()}
        return self.things[key]

    def parse_statement(self,statement):
        """
        parse a statement from the input file a self.things or attribute
        """
        # code to handle events
        m = RE_IF.match(statement)
        if m:
            cond = m.group('c').replace(', ',' and ').split(' and ')
            actions = m.group('a').replace(', ',' and ').split(' and ')
            if not cond[0].startswith('you '):
                return False
            verb, name = cond[0][4:].split(' ',1)
            article, key = split(name)
            thing = self.get_or_store_thing(key)
            cause = []
            for other_condition in cond[1:]:
                for name, regex in REGEX:
                    m = regex.match(other_condition)
                    if m:
                        cause.append((name,m.groupdict()))
                        break
            effect = []
            for action in actions:
                for name, regex in REGEX:
                    m = regex.match(action)
                    if m:
                        if m.group('o'):
                            self.get_or_store_thing(m.group('o'))
                        effect.append((name,m.groupdict()))
                        break
                else:
                    return False
            events = thing['events'][verb] = thing['events'].get(verb,set()) 
            events.add(Event(self.things,cause,effect))
            return True
        # code to handle status
        for name, regex in REGEX:
            m = regex.match(statement)
            if m:
                thing = self.get_or_store_thing(m.group('s'))
                if name == 'attr':
                    thing['attr'][m.group('k')] = m.group('v')
                elif name == 'can':
                    if thing['name'] != 'you':
                        return False
                    obj = self.get_or_store_thing(m.group('o'))
                    obj['events'][m.group('v')] = set()
                else:
                    if name == 'says':
                        thing[name] = m.group('o')
                    else:
                        other = self.get_or_store_thing(m.group('o'))
                        thing[name].add(other['name'])
                        if name == 'to':
                            other['is'].add('place')
                return True
        else:
            return False

    def pretty_print(self):
        for key in sorted(self.things):
            thing = self.things[key]
            print thing['name']
            for key,value in thing.items():
                if value:
                    print '  - %s: %s' % (key,value)

    def enter_place(self, fullname, force=False):
        """
        for example game.enter_place('the bedroom')
        on success returns the message associated to the new place
        on error raises an exception
        """
        article, name = split(fullname)
        if not name in self.things:
            raise Message("%s is unknown" % fullname)
        thing = self.things[name]
        if not 'place' in thing['is']:
            raise Message("%s is not a place" % fulltime)
        you = self.things['you']
        if name in you['in']:
            raise Message('you are in %s already' % fullname)
        things = [self.things[key] for key in self.visible()]
        places = reduce(lambda a,b:a|b,
                        [thing['to'] for thing in things if
                         not 'locked' in thing['is']],set())
        if force or name in places:
            self.things['you']['in'] = set([name])
            return self.things[name]['says'] or ''
        raise Message("no known way to get to %s" % fullname)

    def can_see(self,name,taken=True):
        """
        game.can_see('the cat') -> True or False
        """
        thing = self.things.get(name,None)
        if not thing:
            raise Message("%s is unkown" % name)
        you = self.things['you']
        if taken and thing['name'] in you['has']:
            return True
        if 'invisible' in thing['is']:
            return False
        return (name in you['in'] or you['in'].intersection(thing['in']))

    def visible(self):
        """
        returns a list of names of visible things
        """
        return [name for name in self.things if self.can_see(name,taken=False)]

    def join(self,items):
        """
        joins the list of items after adding articles
        """
        return ', '.join('%(article)s%(name)s' % self.things[item] for item in items)

    def take_thing(self, name):
        """
        take a thing by adding to self.things['you']['has']
        """
        article, name = split(name)
        if name == 'you':
            raise Message('you cannot lift yourself!')
        you = self.things['you']
        if self.can_see(name):
            thing = self.things[name]
            for k in ('in','on','under','near'):
                thing[k].clear()
            you['has'].add(name)
        else:
            raise Message("%s is unkown" % name)

    def drop_thing(self, name):
        """
        drop something you have in the your currently are
        """
        article, name = split(name)
        you = self.things['you']
        if name in you['has']:
            thing = self.things[name]
            thing['in'] |= you['in']
            you['has'].remove(name)
        else:
            raise Message("you do not have %s" % name)

    def inspect(self, name):
        """
        returns a string with the description of thing name
        """
        article, name = split(name)
        if self.can_see(name):
            thing = self.things[name]
            you = self.things['you']
            s = ''
            fullname = '%s%s' % (article, name)
            v = 'are' if name == 'you' or 'plural' in thing['is'] else 'is'
            if thing['is']:
                s += '%s %s %s\n' %(fullname,v,self.join(thing['is']))
                if thing['in'] - you['in']:
                    s += '%s %s in %s\n' %(fullname,v,self.join(thing['in']-you['in']))
            if thing['on']:
                s += '%s %s on %s\n' %(fullname,v,self.join(thing['on']))
            if thing['under']:
                s += '%s %s under %s\n' %(fullname,v,self.join(thing['under']))
            if thing['near']:
                s += '%s %s near %s\n' %(fullname,v,self.join(thing['near']))
            for key,value in thing['attr'].items():
                s += 'the %s of %s is %s\n' %(key, fullname,value)
            v = 'have' if name == 'you' or 'plural' in thing['is'] else 'has'
            if thing['has']:
                s += '%s %s %s\n' %(fullname,v,self.join(thing['has']))
            if thing['events']:
                s += 'you can %s %s\n' % (
                    ', '.join(thing['events'].keys()), fullname)
            if thing['to']:
                s += 'it leads to %s\n' % (', '.join(thing['to']))
            return s
        else:
            raise Message("%s is unkown" % name)

    #### methods that perform I for user interface

    def where_am_i(self):
        return 'you are %s' % ', '.join('in %s' % key for key
                                        in self.things['you']['in'])

    def who_am_i(self):
        if self.things['you']['is']:
            return 'you are %s' % ', '.join(self.things['you']['is'])
        else:
            return 'unknown'

    def what_do_i_have(self):
        if self.things['you']['has']:
            return 'you have %s' % ', '.join('%(article)s%(name)s' % self.things[key] for key in self.things['you']['has'])
        else:
            return 'nothing'

    def look_around(self):
        names = self.visible()
        return 'you see %s' % ', '.join(
            '%(article)s%(name)s' % self.things[key] for key in names
            if not key == 'you')

    def look_at(self,name):
        return self.inspect(name).rstrip()

    def enter(self,name):
        message = self.enter_place(name)
        return 'you are now in %s\n%s' % (name, message)

    def internals(self):
        self.pretty_print()
        print ''

    def help(self):
        return HELP

    def save(self,filename):
        cPickle.dump(self.things, open(filename,'wb'))
        return 'game saved!'

    def load(self,filename):
        self.things = cPickle.load(open(filename,'rb'))
        return 'game loaded!'

    def take(self,name):
        self.take_thing(name)
        return '%s taken' % name

    def drop(self,name):
        self.drop_thing(name)
        return '%s dopped' % name

    def action(self,verb,name):
        article,key = split(name)
        if self.can_see(key):
            thing = self.things[key]
            if not verb in thing['events']:
                raise Message('you cannot %s %s' % (verb, name))
            messages = []
            for event in thing['events'].get(verb,set()):
                messages.append(event())
            return '\n'.join(messages) or 'nothing happened'
        return "not allowed"

    def do_not_understand(self):
        return 'sorry, I do not understand'

    def loop(self, echo=False):
        """
        plays the game stored in self.things
        loops and asks the player to take an action
        the playe can:
        - look around
        - look at a thing
        - take a thing
        - drop a thing
        - enter a place
        - <verb> <a thing>
        - save the state
        - load the state
        """
        for place in self.things['you']['in']:
            message = self.things[place]['says']
            if message:
                print message
        while True:
            command = RE_CLEAN.sub(' ',raw_input('YOU> ').strip())
            if echo: print command
            for regex, func_name in INPUT:
                match = regex.match(command)
                if match:
                    try:
                        message = getattr(self,func_name)(**match.groupdict())
                        print message
                        if message and 'won the game!' in message:
                            return
                    except Message, e:
                        print e
                    break
            else:
                print self.do_not_understand()

    def play(self,echo=False):
        """
        starts the main loop
        """
        try:
            self.loop(echo=echo)
        except (EOFError, KeyboardInterrupt):
            print

SAMPLE="""
you are in the bedroom
the bedroom is a place
the bedroom says "hello to you!"
a green door is in the bedroom
the green door is locked
the green door leads to the bathroom
the cat is in the bedroom
the table is in the bedroom
the cat is on the table
a blue key is in the bedroom
the blue key is under the table
the blue key is invisible
the color of the cat is red
the cat has a backpack
if you poke the cat then the cat says "kick the table"
if you kick the table then the blue key is visible
if you use the blue key and you have the blue key then the green door is unlocked
the bathroom says "you made it here and won the game!"
"""

if __name__ == '__main__':
    input = open(sys.argv[1]).read() if len(sys.argv)>1 else SAMPLE
    echo = len(sys.argv)>2 and sys.argv[2]=='echo'
    Game(input).play(echo=echo)
