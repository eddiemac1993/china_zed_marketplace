from django.templatetags.static import static


class MobileAppHeadMiddleware:
    """
    Adds installable mobile-app metadata to regular HTML pages.
    Keeping it here avoids repeating the same tags across every template.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        content_type = response.get("Content-Type", "")
        if (
            request.path.startswith("/admin/")
            or "text/html" not in content_type
            or response.streaming
            or response.status_code >= 400
        ):
            return response

        try:
            html = response.content.decode(response.charset or "utf-8")
        except UnicodeDecodeError:
            return response

        if "</head>" not in html or 'rel="manifest"' in html:
            return response

        app_head = f"""
    <meta name="theme-color" content="#E5141A">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-title" content="ChinaZed">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <link rel="manifest" href="{static('core/manifest.webmanifest')}">
    <link rel="apple-touch-icon" href="{static('core/images/market-icon-180.png')}">
    <script>
        if ("serviceWorker" in navigator) {{
            window.addEventListener("load", function () {{
                navigator.serviceWorker.register("/service-worker.js").catch(function () {{}});
            }});
        }}
    </script>
"""
        response.content = html.replace("</head>", f"{app_head}</head>", 1).encode(response.charset or "utf-8")
        response["Content-Length"] = str(len(response.content))
        return response
