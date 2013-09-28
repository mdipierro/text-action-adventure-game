"""
to do better links object to subject
take, drop, poke, poked, lock, unlock, locked
"""
import re
import sys

#input = input.replace('\n','.').replace(';','.')

re_blocks = re.compile('\[(?P<key>.*?)\]\s+(?P<value>[^\[]+)\s+',re.DOTALL)
re_cleanup_spaces = re.compile("[ \t]+")
re_cleanup_punctuation = re.compile("[ \t]*([\.:;,])[ \t]*") 
re_cleanup_arrows = re.compile("[ \t]*(\-\>)[ \t]*") 
RE = RuntimeError

HELP = """
where am I?
who am I?
what do I have?
what can I do?
look around
look at the <thing>
move to <room>
take <thing>
drop <thing>
use <thing> to <verb> <thing>
say <something>
"""

def getlines(text):
    """
    break a block of text into a list of non-empty lines
    """
    lines = []
    for line in text.split('\n'):
        line = line.strip()
        if line and not line.startswith('#'):
            lines.append(line)
    return lines

def break_article(subj):
    """
    separate "a black cat" into (subject, article) = ("black cat", "a")
    """
    parts = subj.split(' ',1)
    if len(parts)>1 and parts[0] in ('a','an','the'):
        subj = parts[-1]
        article = parts[0]
    else:
        article = 'the'
    return subj, article

def parse(input):
    """
    parses an input files into a dictionary representing the game.
    a game has:
    - places (which have name, description, doors)
    - things (which are, have, can, etc.)
    - start place
    """
    game = {'places':{}, 'things':{}, 'start':None}
    input = re_cleanup_spaces.sub(' ',input)
    input = re_cleanup_punctuation.sub('\g<1> ',input)
    input = re_cleanup_arrows.sub(' \g<1> ',input)
    blocks = dict(re_blocks.findall(input))
    if not 'PLACES' in blocks:
        raise RE('Missing [PLACES] part')
    for line in getlines(blocks['PLACES']):
        if not ':' in line:
            raise RE('Invalid line: %s' % line)
        name, description = line.split(': ',1)
        game['places'][name] = {
            'name':name,
            'description':description,
            'doors':{'open':[],'closed':[]},
            'contains':[]}
        if not game['start']:
            game['start'] = name
    if not 'DOORS' in blocks:
        raise RE('Missing [DOORS] part')
    for line in getlines(blocks['DOORS']):
        if line.count(': ')!=2:
            raise RE('Invalid line: %s' % line)
        room1, room2, status = line.split(': ',2)
        if not room1 in game['places']:
            raise RE('Invalid line: %s (unknown room)' % line)
        if not room2 in game['places']:
            raise RE('Invalid line: %s (unknown room)' % line)
        if not status in ('open', 'closed'):
            raise RE('Invalid line: %s (unknown status)' % line)
        game['places'][room1]['doors'][status].append(room2)
    if not 'THINGS' in blocks:
        raise RE('Missing [THINGS] part')
    last = None
    def add_thing(subj,verb=None,obj=None):
        subj,article = break_article(subj)
        if not subj in game['things']:
            game['things'][subj] = {'name':subj, 'article':article}
        if verb in ('is', 'are'):
            parts = obj.split(' ',1)
            if len(parts)==2 and parts[0] in ('in','on','over','under','near'):
                verb, obj = '%s %s' % (verb, parts[0]), parts[1]
        if verb:
            if not verb in game['things'][subj]:
                game['things'][subj][verb] = []            
            game['things'][subj][verb].append(obj)
            obj = add_thing(obj)
            if verb.endswith(' in') and obj in game['places']:
                game['places'][obj]['contains'].append(subj)
        return subj
    add_thing('player')
    for line in getlines(blocks['THINGS']):
        for verb in ('is','has','are','have','can'):
            if ' %s ' % verb in line:
                subj, obj = line.split(' %s ' % verb)                
                if subj in ('it','he','she','they'):
                    if last:
                        subj = last
                    else:
                        raise RE('Invalid line: %s (unknown subect)' % line)
                last = subj
                add_thing(subj,verb,obj)
                break
        else:
            raise RE('Invalid line: %s' % line)
    return game

def commajoin(items, logic='and'):
    """
    takes a list of items and returns a comma separated string.
    for example:
    ['one']                 -> 'one'
    ['one', 'two']          -> 'one and two'
    ['one', 'two', 'three'] -> 'one, two, and three'
    """
    if len(items)==0:
        return ''
    elif len(items)==1:
        return items[0]
    ret = ', '.join(items[:-1])
    if len(items)>2: ret = ret + ','
    ret = ret + ' %s %s' % (logic,items[-1])
    return ret

def play(game):
    """
    plays the game stored in the dict game.
    loops and asks the player to take an action
    the playe can:
    - instect a place
    - inspact a thing
    - change the state of thing (take, drop, use, poke, etc.)
    - change his own state (take, drop)
    """
    status = {'room': game['places'][game['start']], 
              'has': game['things']['player']['has'],
              'is': game['things']['player']['is'],
              'can': game['things']['player']['can']}
    while True:
        room = status['room']
        command = re_cleanup_spaces.sub(' ',raw_input('> ').strip())
        if command == 'help':
            print HELP
        elif command == 'where am I?':
            print "in %s" % room['name']
            print room['description']
        elif command == 'who am I?':
            print commajoin(status['is'])
        elif command == 'what do I have?':
            print commajoin(status['has'])
        elif command == 'what can I do?':
            print commajoin(status['can'], logic='or')
        elif command == 'look around':            
            n = len(room['doors']['open'])
            m = len(room['doors']['closed'])
            if not n+m:
                s = 'I see no doors'
            elif m:
                s = 'I see %s closed door%s' % (n, '' if n==1 else 's') 
            if n:
                s += ' and %s open door%s' % (n or 'no', '' if n==1 else 's')
                s += ' leading to %s' % commajoin(room['doors']['open'])
            print s
            if len(room['contains']):
                things = commajoin(['%s %s' % (
                            game['things'][name]['article'], name)
                                    for name in room['contains']])
                print "I also see %s" % things
        elif command.startswith('look at '):
            obj, article = break_article(command[8:])
            objs = [o for o in room['contains'] if o.startswith(obj)]
            if len(objs) == 0:
                print 'there is no %s' % obj
            elif len(objs) > 1:
                print 'which %s? %s?' % '? '.join(objs)
            else:
                for key, value in game['things'][objs[0]].items():
                    if key=='is in':
                        value = [v for v in value if v != room['name']]
                    if isinstance(value,list) and value:
                        print '%s %s %s %s' % (article, obj, key, 
                                               commajoin(value))
        elif command.startswith('enter '):
            name = command[6:]
            if name in room['doors']['closed']:
                print "I cannot, the door is closed"
            elif not name in room['doors']['open']:
                print "There is no %s" % name
            else:
                room = status['room'] = game['places'][name]
                print status['room']['description']
        else:
            print 'what?'

game = parse(open(sys.argv[1]).read())
print game
play(game)
