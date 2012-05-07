#!/usr/bin/env python

import re
import datetime
import dateutil.parser
import subprocess

class TmuxCmd(object):
    @staticmethod
    def kwargs_to_flags(kwargs):    
        for k,v in kwargs.items():
            # command flags are 'True' if they are present, 
            # and 'False' if they are absent
            if v is True:
                kwargs[k] = ''

            if v is False:
                del kwargs[k] 

        # FIXME this is certainly not pythonic
        flags = filter(lambda x: len(x)>0,sum([['-'+k[0] if len(k)>1 and not k.startswith('-') else k,v] for (k,v) in kwargs.items()], []))
        return tuple(flags)

    @staticmethod
    def open_tmux(args):
        return subprocess.Popen(['/opt/local/bin/tmux'] + args, stdout=subprocess.PIPE)

    @staticmethod 
    def cmd(*args, **kwargs):

        flags = TmuxCmd.kwargs_to_flags(kwargs)
        cmd = args[0]
        tmux = TmuxCmd.open_tmux([cmd] + list(flags) + list(args[1:]))
        (stdout, stderr) = tmux.communicate()

        if stdout is None or len(stdout) == 0:
            return None
        else:
            return stdout.strip()

    @staticmethod
    def returncode(*args, **kwargs):
        flags = TmuxCmd.kwargs_to_flags(kwargs)
        cmd = args[0]
        tmux = TmuxCmd.open_tmux([cmd] + list(flags) + list(args[1:]))
        (stdout, stderr) = tmux.communicate()
        return tmux.returncode



    def __init__(self, target, cmd):
        self.target = target
        self.cmd = cmd


    def __call__(self, *args, **kwargs):
        args = (self.cmd,) + args
        return self.target.cmd(*args, **kwargs)

class TmuxClass(type):
    def __iter__(cls):
        for obj in cls.all_objs():
            yield obj

class TmuxObject(object):

    __metaclass__ = TmuxClass
    @staticmethod
    def to_pyval(val):
        ''' Take a tmux-option-style value and return a corresponding
        python-style value that makes sense.

        On-off tmux options may have the value 'on' or 'off'. These
        are mapped to python booleans: 'on' becomes True, and 'off' becomes False.
        tmux values which are integers are mapped to ints. The string 'none' is mapped
        to the NoneType. All other values are left as they are.

        '''

        if val == 'on':
            return True
        
        elif val == 'off':
            return False

        elif val == 'none':
            return None

        elif val.isdigit():
            return int(val)

        else:
            return val

    @staticmethod
    def to_tmuxval(val):
        '''Take a python-style value and return a corresponding tmux-style-style value that makes sense.'''
        if val is True:
            return 'on'
        
        elif val is False:
            return 'off'

        elif val is None:
            return 'none'

        elif isinstance(val, int):
            return str(x)

        else:
            return val

    @staticmethod
    def normalizecmd_name(name):
        '''Turn a tmux command name into a legal python identifier'''
        return name.replace('-', '_')

    def __init__(self):
        for cmd in self.__class__._supported_cmds:
            method_name = TmuxObject.normalizecmd_name(cmd)
            if not hasattr(self, method_name):
                self.__dict__[method_name] = TmuxCmd(self, cmd)

    def __eq__(self, other):
        return self._name == other._name

    def cmd(self, *args, **kwargs):
        '''Execute the given command on this TmuxObject'''
        kwargs['target'] = self._name
        return TmuxCmd.cmd(*args, **kwargs)

    def returncode(self, *args, **kwargs):
        kwargs['target'] = self._name
        return TmuxCmd.returncode(*args, **kwargs)

    def show_options(self,optionscmd, global_=False):
        '''Show the options currently applied to this TmuxObject

        This method returns a dictionary mapping tmux options to python
        values.
        '''
        g=global_
        opt_dict = {}
        optlist = self.cmd(optionscmd, global_=g)

        if optlist is None:
            return {}

        opts = [opt.split(' ') for opt in optlist.split('\n')]

        for opt in opts:
            if len(opt) > 2:
                opt = [opt[0], ' '.join(opt[1:])]
                        
            opt_dict.update({opt[0]: TmuxObject.to_pyval(opt[1])})
        return opt_dict

    # Allow pythonic access to tmux options:
    #
    # some_session.status_bg = white
    #
    # if my_session.status_keys == 'emacs':
    #     my_session.status_keys = 'vi'
    #
    # Python identifiers can't have hyphens in them, but tmux options can, 
    # so hyphens are normalized to underscores
    def __setattr__(self, attr, value):
        if attr.startswith('_'):
            self.__dict__[attr] = value
        else:
            attr = attr.replace('_', '-')
            self.set_option(attr, TmuxObject.to_tmuxval(value))

    def __getattr__(self, attr):
        if attr.startswith('_'):
            raise AttributeError

        attr = attr.replace('_', '-')
        instopts = self.show_options()
        globalopts = self.show_options(global_=True)

        if attr in instopts:
            return instopts[attr]
        elif attr in globalopts:
            return globalopts[attr]
        else:
            raise AttributeError

    @property
    def name(self):
        return self._name


class Session(TmuxObject):
    _supported_cmds = ['list-windows',
                'kill-session',
                'has_session',
                'attach-session',
                'list-clients',
                'lock-session',
                'list-bindings',
                'next-window',
                'previous-window',
                'select-window',
                'set-option',
                'show-options',
               ]

    @staticmethod
    def all_objs():
        ''' Return all Sessions currently tracked by the server'''
        session_list = TmuxCmd.cmd('list-sessions')

        if session_list is None:
            raise StopIteration

        for session_info in session_list.split('\n'):
            name = session_info.partition(':')[0]
            yield Session(name)

    @staticmethod
    def all_sessions():
        for i in Session.all_objs():
            yield i

    @staticmethod
    def list_sessions():
        return list(Session)
    
    def __init__(self, _name):
        TmuxObject.__init__(self)
        self._name = _name

    def __len__(self):
        '''Return the number of windows associated with this session'''
        return sum(1 for window in self)

    def __repr__(self):
        return '<%s %s: %d Windows (created %s) [%s] %s>' % (self.__class__.__name__,
                                                               self.name,
                                                               len(self),
                                                               self.creation_date,
                                                               self.size,
                                                               '(attached)' if self.is_attached else '')

    def __str__(self):
        session_list = TmuxCmd.cmd('list-sessions')

        if session_list is None:
            return None

        for desc in session_list.split('\n'):
            if desc.partition(':')[0] == self.name:
                return desc

        else:
            raise Exception    

    def __getitem__(self,idx):
        return window #fixme
               
    def rename_session(self, newname):
        '''Change the name of this session'''
        self.cmd('rename-session', newname)
        self._name = newname

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, newname):
        rename_session(newname)


    # More pythonic access to Windows:
    # for window in Session('mysession'):
    # Window('irssi') in Session('mysession')
    def __iter__(self):
        for w in self.windows():
            yield w

    def windows(self):
        '''Return all the windows associated with this session'''
        window_list = self.cmd('list-windows')
        if window_list is None:
            raise StopIteration

        for desc in window_list.split('\n'):
            num = int(desc.partition(':')[0])
            yield Window(self, num)

    def window(self, window_name):
        if isinstance(window_name, int):
            for w in self:
                if w.number == window_name:
                    return w

            raise IndexError
        else:
            raise NotImplementedError #FIXME

        raise ValueError, 'Window %s doesn\'t exist' % window_name

    def __getitem__(self, window_name):
        return self.window(window_name)

    def list_windows(self):
        return list(self.windows())

    def show_options(self,global_=False):
        g = global_ 
        return TmuxObject.show_options(self, 'show-options', global_=g)

    def kill(self):
        self.kill_session()

    def lock(self):
        self.lock_session()

    @property
    def size(self):
        match = re.findall('\[(\d+x\d+)\]', str(self))
        return match.pop()

    @property
    def width(self):
        return int(self.size.partition('x')[0])

    @property
    def height(self):
        return int(self.size.partition('x')[2])
    
    @property
    def creation_date(self):
        match = re.findall('\(created(.*?)\)', str(self))
        #FIXME: rewrite this with datetime.strptime
        return dateutil.parser.parse(match.pop())

    @property
    def is_attached(self):
        return '(attached)' in str(self)
    
    @property
    def exists(self):
        return self.returncode('has-session') == 0


class Window(TmuxObject):
    _supported_cmds = [
        'choose-client',
        'choose-session',
        'choose-window',
        'display-panes',
        'kill-window',
        'last-pane',
        'next-layout',
        'previous-layout',
        'respawn-window',
        'rotate-window',
        'select-layout',
        'select-window',
        'unlink-window',
        'set-window-option',
        'find-window',
    ]

    def __init__(self, parent_session, num):
        TmuxObject.__init__(self)
        self._parent_session = parent_session
        self._num = num

    def rename_window(self, newname):
        # FIXME
        self.cmd('rename-window', newname)
        self._name = newname

    def set_option(self, *args, **kwargs):
        return self.set_window_option(*args, **kwargs)

    def show_options(self,global_=False):
        g = global_ 
        return TmuxObject.show_options(self, 'show-window-options', global_=g)

    @property
    def number(self):
        return self._num

    @property
    def parent_session(self):
        return self._parent_session

    @property
    def name(self):
        return '%s:%d' % (self.parent_session.name, self.number)

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self.name)

