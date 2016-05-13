# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# Copyright (c) 2015 Reishin <hapy.lestat@gmail.com>

import os
import sys
import json

from appcore.core import aLogger


class CommandLineAST(object):
  def __init__(self, args, out_tree):
    """
    :arg args List of arguments to parse
    :arg out_tree Hash map tree, already initialized at least with root element

    :type out_tree dict
    :type args list
    """
    self.__default_arg_tag = "default"
    self._log = aLogger.getLogger(self.__class__.__name__, default_level=aLogger.Level.error)
    self.__args = list(args)
    self.__out_tree = out_tree

  def parse(self):
    """
    Parse command line to out tree
    """
    if self.__out_tree is None:
      raise RuntimeError("Could'n use empty out tree as ast storage")

    if isinstance(self.__out_tree, dict):
      self.__out_tree[self.__default_arg_tag] = []

    if len(self.__args) >= 1:
      self.__args.pop(0)
      self._log.info("Passed commandline arguments: %s", self.__args)

    for param in self.__args:
      if self._is_default_arg(param):
        self.__out_tree[self.__default_arg_tag].append(param.strip())
      else:
        param = param.lstrip("-").partition('=')
        if len(param) == 3:
          self.__parse_one_param(param)

  def _is_default_arg(self, param):
    """
    Check if passed arg belongs to default type
    :type param str
    :rtype bool
    """
    param = param.strip()
    restricted_symbols = ["=", "-"]
    for symbol in restricted_symbols:
      if symbol in param:
        return False

    return True

  def __set_node(self, node, key, value):
    if not isinstance(node, dict):
      self._log.error("Invalid assignment to {0}", key)
      return

    if key in node and isinstance(node[key], dict) and not isinstance(value, dict):
      self._log.error("Invalid assignment to {0}", key)
      return

    node[key] = value

  def __parse_one_param(self, param):
    """
    :argument param tuple which represents arg name, delimiter, arg value
    :type param tuple
    """
    self._log.debug("Parse param \'%s\' with value \'%s\'", param[0], param[2])
    keys = param[0].split('.')
    if len(keys) == 1:  # parse root element
      self._log.debug("Replacing param \'%s\' to value \'%s\'", keys[0], param[2])
      self.__set_node(self.__out_tree, keys[0], param[2])
    elif len(keys) > 0:
      item = self.__out_tree
      for i in range(0, len(keys)):
        key = keys[i]
        is_last_key = i == len(keys) - 1
        if key not in item:
          self.__set_node(item, key, "" if is_last_key else {})

        if is_last_key and key in item and not isinstance(item[key], dict):
          self.__set_node(item, key, param[2])
        elif key in item and isinstance(item, dict):
          item = item[key]
        else:
          self._log.error("Couldn't recognise parameter \'%s\'", param[0])
          break
    else:
      self._log.error("Couldn't recognise parameter \'%s\'", param[0])


class Configuration(object):
  _location = ""
  _script = "__main__"
  _log = None
  _config_path = "conf/"
  _main_config = "main.json"
  _json = None

  def normalize_path(self, path):
    return path.replace('/', os.path.sep)

  def __init__(self, in_memory=False, config_path=None, config_name=None):
    """
    :arg in_memory Initialize Configuration instance in memory only
    :type in_memory bool
    :type config_path str
    :type config_name str
    """
    mypackage = str(__package__)
    self._location = os.path.dirname(sys.argv[0])
    if self._location.strip() == "":
      self._location = "."

    if sys.argv is not None and len(sys.argv) > 0:
      self._script = os.path.basename(sys.argv[0])

    self.__in_memory = bool(in_memory)

    if self._location.endswith(__package__):
      self._location = self._location[:-len(__package__) - 1]

    self._log = aLogger.getLogger(__name__, default_level=aLogger.Level.error)  # initial logger

    self._main_config = "main.json" if config_name is None else config_name
    self._config_path = self.normalize_path("%s/%s" % (self._location, self._config_path)) if config_path is None else config_path
    self.load()

  @property
  def conf_location(self):
    return self._config_path

  @property
  def location(self):
    return self._location

  @property
  def script_filename(self):
    return self._script

  def _load_from_configs(self, filename):
    """
     Return content of file which located in configuration directory
    """
    config_filename = "%s%s" % (self._config_path, filename)
    if os.path.exists(config_filename):
      try:
        f = open(config_filename, 'r')
        content = ''.join(f.readlines())
        f.close()
        return content
      except Exception as err:
        self._log.error("Error in opening config file: %s", err)
        raise err
    else:
      self._log.error("File not found: %s", config_filename)
      raise IOError("File not found: %s" % config_filename)

  def load(self):
    """
     Load application configuration
    """
    try:
      if not self.__in_memory:
        self._json = json.loads(self._load_from_configs(self._main_config))
        self._log = aLogger.getLogger(__name__, cfg=self)  # reload logger using loaded configuration
        self._log.info("Loaded main settings: %s", self._main_config)
        self._load_modules()
      else:
        self._json = {}
      # parse command line, currently used for re-assign settings in configuration, but can't be used as replacement
      self._load_from_commandline()
    except Exception as err:
      self._json = None
      self._log.error("Error in parsing or open config file: %s", err)
      raise err

  def _load_modules(self):
    """
    Load modules-related configuration listened in modules section
     Before loading:
      "modules": {
      "mal": "myanimelist.json",
      "ann": "animenewsnetwork.json"
     }
     After loading:
       "modules": {
        "mal": {
         ....
        },
        "ann": {
         ....
        }
      }
    """
    if self.exists("modules"):
      for item in self._json["modules"]:
        try:
          json_data = json.loads(self._load_from_configs(self._json["modules"][item]))
          self._json["modules"][item] = json_data
          self._log.info("Loaded module settings: %s", item)
        except Exception as err:
          self._log.error("Couldn't load module %s configuration from %s: %s",
                          item,
                          self._json["modules"][item],
                          err)

  def _load_from_commandline(self):
    ast = CommandLineAST(list(sys.argv), self._json)
    ast.parse()

  def exists(self, path):
    """
    Check for property existence
    :param path: path to the property with name including
    :return:
    """
    if self._json is None:
      return False

    node = self._json
    path = path.split('.')
    while len(path) > 0:
      path_item = path.pop(0)
      if path_item in node and len(path) == 0:
        return True
      elif path_item in node and len(path) > 0:
        node = node[path_item]
      else:
        return False

    return False

  def get(self, path, default=None, check_type=None, module=None):
    """
    Get option property

    :param path: full path to the property with name
    :param default: default value if original is not present
    :param check_type: cast param to passed type, if fail, default will returned
    :param module: get property from module name
    :return:
    """
    if self._json is not None:
      # process whole json or just concrete module
      node = self._json if module is None else self.get_module_config(module)
      path_data = path.split('.')
      try:
        while len(path_data) > 0:
          node = node[path_data.pop(0)]

        if check_type is not None:
          return check_type(node)
        else:
          return node
      except KeyError:
        if default is not None:
          self._log.warning("Key %s not present, using default %s" % (path, default))
          return default
        else:
          self._log.error("Key %s not present" % path)
          raise KeyError
      except ValueError:
        if default is not None:
          self._log.warning("Key %s has a wrong format, using default %s" % (path, default))
          return default
        else:
          self._log.error("Key %s has a wrong format" % path)
          raise KeyError
    else:
      return ""

  def get_module_config(self, name):
    """
     Return module configuration loaded from separate file or None
    """
    self._log.debug("Getting module configuration %s", name)
    if self.exists("modules"):
      if name in self._json["modules"] and not isinstance(self._json["modules"][name], str):
        return self._json["modules"][name]
    return None


__conf = None


def get_instance(in_memory=False, config_path=None, config_name=None):
  """
  :arg in_memory Initialize Configuration instance in memory only
  :type in_memory bool
  :type config_path str
  :type config_name str
  :rtype Configuration
  :return Configuration
  """
  global __conf

  if __conf is None:
    __conf = Configuration(in_memory=in_memory, config_path=config_path, config_name=config_name)

  return __conf
