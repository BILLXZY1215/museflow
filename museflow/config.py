import sys


_NO_DEFAULT = object()


class Configurable:
    _subconfigs = []

    def __init__(self, config=None):
        self._config_dict = config or {}

    def _configure(self, config_key, constructor=None, **kwargs):
        config = self._get_config(config_key, default={})

        if type(config) is not dict:
            if constructor or kwargs:
                raise ConfigError('Error while configuring {}: dict expected, got {}'.format(
                    config_key, type(config)
                ))
            return config

        try:
            config_dict = dict(config)  # Make a copy of the dict

            if not constructor or 'class' in config_dict:
                constructor = config_dict['class']
                del config_dict['class']
        except Exception as e:
            raise ConfigError('{} while configuring {}: {}'.format(
                type(e).__name__, config_key, e
            )).with_traceback(sys.exc_info()[2]) from None

        try:
            if issubclass(constructor, Configurable):
                return constructor.from_config(config_dict, **kwargs)

            kwargs = dict(kwargs)
            kwargs.update(config_dict)
            return constructor(**kwargs)
        except TypeError as e:
            raise ConfigError('{} while configuring {} ({!r}): {}'.format(
                type(e).__name__, config_key, constructor, e
            )).with_traceback(sys.exc_info()[2]) from None

    def _get_config(self, key, default=_NO_DEFAULT):
        if default is _NO_DEFAULT:
            return self._config_dict[key]
        return self._config_dict.get(key, default)

    @classmethod
    def from_config(cls, config, *args, **kwargs):
        kwargs = dict(kwargs)
        kwargs.update({k: v for k, v in config.items() if k not in cls._subconfigs})
        config = {k: v for k, v in config.items() if k in cls._subconfigs}

        return cls(*args, **kwargs, config=config)


class ConfigError(Exception):
    pass