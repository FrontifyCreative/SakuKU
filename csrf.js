// Menempelkan token CSRF ke semua request yang mengubah data (POST/PUT/PATCH/DELETE).
(() => {
  const token = () => document.querySelector('meta[name="csrf-token"]')?.content || "";
  const nativeFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    const method = (init.method || (input && input.method) || "GET").toUpperCase();
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      const headers = new Headers(init.headers || (input && input.headers) || {});
      headers.set("X-CSRF-Token", token());
      init = { ...init, headers };
    }
    return nativeFetch(input, init);
  };
})();
