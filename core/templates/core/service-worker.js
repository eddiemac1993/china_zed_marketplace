const CACHE_NAME = "chinazed-app-v1";
const APP_SHELL = [
    "/",
    "/login/",
    "/register/",
    "/static/core/manifest.webmanifest",
    "/static/core/images/chinazed-icon-192.png",
    "/static/core/images/chinazed-icon-512.png"
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
