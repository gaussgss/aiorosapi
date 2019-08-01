#
# -+- coding: utf-8 -+-


class RosApiException(Exception): pass


class RosApiDataException(RosApiException): pass
class RosApiSentenceOrderException(RosApiDataException): pass


class RosApiProtocolException(RosApiException): pass
class RosApiConnectionLostException(RosApiProtocolException): pass
class RosApiCommunicationException(RosApiProtocolException): pass


class RosApiCommandException(RosApiException): pass
class RosApiTrapException(RosApiCommandException): pass
class RosApiFatalException(RosApiCommandException): pass

class RosApiNoResultsException(RosApiCommandException): pass
class RosApiTooManyResultsException(RosApiCommandException): pass
class RosApiLoginFailureException(RosApiCommandException): pass

