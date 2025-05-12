from .models import SiteVisit


class TrafficLoggerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.user.is_staff and not request.path.startswith("/admin"):
            SiteVisit.objects.create(
                ip_address=request.META.get("REMOTE_ADDR", ""),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
                path=request.path,
            )
        return response
