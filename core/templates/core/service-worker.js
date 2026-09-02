const CACHE_NAME = "chinazed-app-v3";
const APP_SHELL = [
    "/",
    "/login/",
    "/register/",
    "/static/core/manifest.webmanifest",
    "/static/core/images/market-icon-192.png",
    "/static/core/images/market-icon-512.png"
];

self.addEventListener("install", function (event) {
    event.waitUntil(
        caches.open(CACHE_NAME).then(function (cache) {
            return cache.addAll(APP_SHELL);
        }).catch(function () {})
    );
    self.skipWaiting();
});

self.addEventListener("activate", function (event) {
    event.waitUntil(
        caches.keys().then(function (keys) {
            return Promise.all(
                keys.filter(function (key) {
                    return key !== CACHE_NAME;
                }).map(function (key) {
                    return caches.delete(key);
                })
            );
        })
    );
    self.clients.claim();
});

self.addEventListener("fetch", function (event) {
    const request = event.request;

    if (request.method !== "GET") {
        return;
    }

    if (request.mode === "navigate") {
        event.respondWith(
            fetch(request)
                .then(function (response) {
                    const copy = response.clone();
                    caches.open(CACHE_NAME).then(function (cache) {
                        cache.put(request, copy);
                    });
                    return response;
                })
                .catch(function () {
                    return caches.match(request).then(function (cached) {
                        return cached || caches.match("/");
                    });
                })
        );
        return;
    }

    // Only static assets are safe to serve cache-first. Live endpoints — chat
    // polling, search, anything returning JSON — would otherwise be frozen at
    // their first response, because nothing here ever revalidates.
    if (!new URL(request.url).pathname.startsWith("/static/")) {
        return;
    }

    event.respondWith(
        caches.match(request).then(function (cached) {
            return cached || fetch(request).then(function (response) {
                if (response.ok) {
                    const copy = response.clone();
                    caches.open(CACHE_NAME).then(function (cache) {
                        cache.put(request, copy);
                    });
                }
                return response;
            });
        })
    );
});


self.addEventListener("push", function (event) {
    if (!event.data) {
        return;
    }

    let data;
    try {
        data = JSON.parse(event.data.text());
    } catch (e) {
        data = { head: "ChinaZed", body: event.data.text() };
    }

    event.waitUntil(
        self.registration.showNotification(data.head || "ChinaZed", {
            body: data.body || "",
            icon: data.icon || "/static/core/images/market-icon-192.png",
            data: { url: data.url || "/" }
        })
    );
});

self.addEventListener('notificationclick', function (event) {
    event.notification.close();
    var targetUrl = event.notification.data && event.notification.data.url
        ? event.notification.data.url
        : '/';
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
            for (var i = 0; i < clientList.length; i++) {
                var client = clientList[i];
                if ('focus' in client) {
                    client.navigate(targetUrl);
                    return client.focus();
                }
            }
            return clients.openWindow(targetUrl);
        })
    );
});
