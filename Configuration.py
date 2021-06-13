import os
import configparser
import logging
from enum import IntEnum, auto

# Configuration of the product
INI_FILENAME = 'philler.ini'
DEFAULT_PRODUCT = 'PRODUCT1'

class CFG(IntEnum):
    """
    The master list of what can be configured with an INI file.
    """
    #SPECIFIC_GRAVITY        = auto()
    #FILL_VOLUME             = auto()
    FILL_WEIGHT             = auto()
    FILL_WEIGHT_MIN         = auto()
    FILL_PRESSURE           = auto()
    FILL_INIT_DISPENSE_TIME = auto()
    FILL_INIT_DISPENSE_MIN  = auto()
    #DISPENSE_RATE           = auto()
    DISPENSE_OFFSET         = auto()
    DISPLAY_PRESSURE        = auto()
    PURGE_TIME              = auto()
    PURGE_MAX_COUNT         = auto()
    TARE_TOLERANCE          = auto()
    BOTTLE_MIN_WEIGHT       = auto()
    CLEAN_DISPENSE          = auto()

DEFAULT_ITEMS = dict()

# Setup the defaults for product 1
DEFAULT_ITEMS[DEFAULT_PRODUCT] = dict({

    # configurable: display name, units, config name, type, default value
    #CFG.SPECIFIC_GRAVITY : ('Specific gravity', 'g/mL', 'product_specific_gravity', float, 0.91),
    #CFG.FILL_VOLUME : ('Fill volume', 'mL', 'fill_volume', float, 30.0),
    CFG.FILL_WEIGHT: ('Fill weight', 'g', 'fill_weight', float, 28.12),
    CFG.FILL_WEIGHT_MIN : ('Fill weight min', 'g', 'fill_weight_min', float, 27.3),  # 28.12 - 3%, for overshoot
    CFG.FILL_PRESSURE : ('Fill pressure (minimum)', 'psi', 'fill_pressure_minimum', float, 18.5),
    CFG.FILL_INIT_DISPENSE_TIME : ('Fill initial dispense time', 'ms', 'fill_init_dispense_time', int, 1500),
    CFG.FILL_INIT_DISPENSE_MIN : ('Fill initial dispense minimum', 'g', 'fill_init_dispense_min', float, 4),
    #CFG.DISPENSE_RATE : ('Dispense rate (slope)', 'g/msec', 'dispense_rate', float, 0.01),
    CFG.DISPENSE_OFFSET : ('Dispense offset (intercept)', 'g', 'dispense_offset', float, 1.5),
    CFG.DISPLAY_PRESSURE : ('Display pressure (maximum)', 'psi', 'pressure_display_max', float, 20.0),
    CFG.PURGE_TIME : ('Purge time', 'ms', 'purge_time', int, 500),
    CFG.PURGE_MAX_COUNT : ('Maximum purges per bottle', 'ct', 'max_purge', int, 5),
    CFG.TARE_TOLERANCE : ('Tare tolerance', 'g', 'tare_tolerance', float, 0.3),
    CFG.BOTTLE_MIN_WEIGHT : ('Minimum bottle weight', 'g', 'min_bottle_weight', float, 40),
    CFG.CLEAN_DISPENSE : ('Cleaning dispense time', 'ms', 'clean_dispense_time', int, 30000),
})


class Configuration():

    class ConfigurableItem():
        """A single configurable item"""
        def __init__(self, displayname, units, configname, value, itemtype):
            self._displayname = displayname
            self._units = units
            self._configname = configname
            self._value = value
            self._itemtype = itemtype

            self._changed = False

        @property
        def displayname(self): return self._displayname

        @property
        def units(self): return self._units

        @property
        def configname(self): return self._configname

        @property
        def value(self): return self._value
        @value.setter
        def value(self, val):
            self._value = val
            self._changed = True

        @property
        def itemtype(self): return self._itemtype

        @property
        def changed(self): return self._changed

    # Singleton instantiation
    _instance = None
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Configuration, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        self.log = logging.getLogger('')

        self.config = None
        self.product = None
        self.configurableItems = dict()

    @property
    def changed(self):
        """Determine if any config items have changed"""
        result = False
        for item in self.configurableItems.values():
            if item.changed:
                result = True

        return result

    def load(self, filename, product):
        """Load the INI file from disk"""
        self.filename = filename
        self.product = product

        if self.config is None:
            self.config = configparser.ConfigParser()
            self.config.add_section(product)

            # Make a second config parser to detect that we have new items to save
            self.configCheck = configparser.ConfigParser()
            self.configCheck.add_section(product)

        # Load the config with the defaults, before overwriting with what's in the ini file
        for configurable, values in DEFAULT_ITEMS[product].items():

            # Break out the configurable properties
            displayname, units, configname, itemtype, defaultvalue = values

            # Assign the properties to the dict inside the configparser
            self.config[product][configname] = f'{defaultvalue}'

        # Create a new INI file if needed
        if not os.path.exists(filename):
            self.log.info(f'Creating a new config file: {filename}')
            self.save()
        else:
            self.config.read(filename)
            self.configCheck.read(filename)

        # Iterate the entries in the file on disk and determine if we have new ones that need saving
        needsSaving = False
        for item, value in self.config[product].items():
            try:
                self.configCheck[product][item]
            except KeyError:
                self.log.debug(f'New INI item detected: {item}')
                needsSaving = True

        if needsSaving:
            self.log.info(f'INI file has new entries and needs saving.')
            self.save()

        # Build the items dictionary
        for configurable, values in DEFAULT_ITEMS[product].items():

            # Break out the configurable properties
            displayname, units, configname, itemtype, defaultvalue = values

            # Create an item instance with the properly typed value
            self.configurableItems[configurable] = self.ConfigurableItem(displayname, units, configname, itemtype(self.config[product][configname]), itemtype)

    def save(self):
        """Save the INI file to disk"""

        # Sync the items to their configs, then save
        for configurable, item in self.configurableItems.items():

            # Update the config instance with any new values
            self.config[self.product][item.configname] = f'{item.value}'

        with open(self.filename, 'w') as configfile:
            self.log.info(f'Saving config file to {self.filename}')
            self.config.write(configfile)

    def get(self, configurable):
        """Get a configurable value with its properties"""
        try:
            # Verify we have an item for the desired configurable value
            item = self.configurableItems[configurable]

            return item.value, item.units, item.displayname, item.itemtype

        except KeyError:
            # Return something sane, but not useful
            return 0.0, 'inv', '(invalid)', float

    def getValue(self, configurable):
        """Get just the value"""
        val, _, _, _ = self.get(configurable)
        return val

    def set(self, configurable, value, save=True):
        """Get a configurable value with its properties"""

        try:
            # Verify we have an item for the desired configurable value
            item = self.configurableItems[configurable]
            oldvalue = item.value
            item.value = value

            self.log.info(f'Changed configurable {configurable}/{item.configname} from {oldvalue} to {value}')

        except KeyError:
            return False

        # Typically we save it to a file unless directed otherwise
        if save:
            self.save()


# -------------------------------------------------------------------------
# Create a single instance of the configuration for global usage
log = logging.getLogger('')
log.info(f'Loading configuration for {DEFAULT_PRODUCT} from {INI_FILENAME}')
config = Configuration()
config.load(filename=INI_FILENAME, product=DEFAULT_PRODUCT)


