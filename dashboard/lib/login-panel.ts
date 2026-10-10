"use client";

import { loginUrl } from "./auth-navigation";

/** All website sign-in actions pass through the CloudTIX login panel. */
export function openLoginPanel(destination = window.location.href): void {
  window.location.assign(loginUrl(destination, window.location.origin));
}
