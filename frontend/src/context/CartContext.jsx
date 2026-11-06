import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { track } from "@/lib/analytics";

const KEY = "av_cart_token";
const CartContext = createContext(null);
const headers = () => (localStorage.getItem(KEY) ? { "X-Cart-Token": localStorage.getItem(KEY) } : {});

// All amounts come from the server; the browser only sends variant ids and quantities.
export const CartProvider = ({ children }) => {
  const { user } = useAuth();
  const [cart, setCart] = useState(null);
  const merged = useRef(null);
  const apply = useCallback((data) => {
    if (data.cart_token) localStorage.setItem(KEY, data.cart_token);
    setCart(data);
    return data;
  }, []);
  const call = useCallback(async (method, url, body) => apply((await api.request({ method, url, data: body, headers: headers() })).data), [apply]);
  const refresh = useCallback(() => call("get", "/cart").catch(() => null), [call]);
  useEffect(() => {
    if (user === undefined) return;
    if (user && localStorage.getItem(KEY) && merged.current !== user.id) {
      merged.current = user.id;
      call("post", "/cart/merge").then(() => localStorage.removeItem(KEY)).catch(() => refresh());
    } else {
      refresh();
    }
  }, [user, call, refresh]);
  const value = {
    cart, refresh, count: cart?.item_count || 0,
    add: (variant_id, quantity, product_slug) => call("post", "/cart/items", { variant_id, quantity }).then((r) => {
      track("add_to_cart", { product_slug: product_slug || "" });
      return r;
    }),
    setQty: (variant_id, quantity) => call("patch", `/cart/items/${variant_id}`, { quantity }),
    remove: (variant_id) => call("delete", `/cart/items/${variant_id}`),
    acceptPrices: () => call("post", "/cart/accept-prices"),
    applyCoupon: (code) => call("put", "/cart/coupon", { code }),
    removeCoupon: () => call("delete", "/cart/coupon"),
    chooseShipping: (vendor_id, method_id) => call("put", "/cart/shipping", { vendor_id, method_id }),
    chooseAddress: (address_id) => call("put", "/cart/address", { address_id }),
    saveForLater: (variant_id) => call("post", `/cart/items/${variant_id}/save-for-later`),
    moveToCart: (variant_id) => call("post", `/cart/saved/${variant_id}/move-to-cart`),
    removeSaved: (variant_id) => call("delete", `/cart/saved/${variant_id}`),
  };
  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
};

export const useCart = () => useContext(CartContext);
