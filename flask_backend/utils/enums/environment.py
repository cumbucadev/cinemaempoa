from enum import Enum


class EnvironmentEnum(str, Enum):
  DEVELOPMENT = 'development'
  PRODUCTION = 'production'