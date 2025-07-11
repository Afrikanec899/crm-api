import functools


def openapi_ready(f):
    """
    The openapi generation needs to be able to call some methods on the viewset
    without a user on the request (or AnonymousUser being on it). drf_yasg sets
    the swagger_fake_view attr on the view when running these methods, so we can
    check for that and call the super method if it's present.  This does mean
    that the super method output still has to makes sense for the docs you're trying
    to generate.
    """

    @functools.wraps(f)
    def wrapped(self, *args, **kwargs):
        if getattr(self, "swagger_fake_view", False):
            # this looks like utter voodoo but it's simply getting the super
            # class, dynamically getattring the method from it and calling that
            # method with the args passed to f
            return getattr(super(self.__class__, self), f.__name__)(*args, **kwargs)
        else:
            return f(self, *args, **kwargs)

    return wrapped
