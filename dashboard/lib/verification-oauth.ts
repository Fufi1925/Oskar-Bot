import { createHmac, randomBytes, timingSafeEqual } from "crypto";

export type VerifyState = { guildId: string; nonce: string; exp: number };
export type VerifyResult = {
  guild_id: string;
  guild_name?: string;
  guild_icon?: string | null;
  status: "success" | "denied" | "error";
  reason?: string;
  role_name?: string;
  blocked?: Array<{ id: string; name: string }>;
  exp: number;
};

function secret(): string {
  const value =
    process.env.VERIFICATION_OAUTH_SECRET || process.env.NEXTAUTH_SECRET;
  if (!value)
    throw new Error("VERIFICATION_OAUTH_SECRET or NEXTAUTH_SECRET is required");
  return value;
}

function encode(value: unknown): string {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}

function signature(body: string): string {
  return createHmac("sha256", secret()).update(body).digest("base64url");
}

function readSigned<T>(token: string): T | null {
  const [body, supplied] = token.split(".");
  if (!body || !supplied) return null;
  const expected = signature(body);
  const a = Buffer.from(supplied);
  const b = Buffer.from(expected);
  if (a.length !== b.length || !timingSafeEqual(a, b)) return null;
  try {
    const value = JSON.parse(Buffer.from(body, "base64url").toString("utf8"));
    if (!value?.exp || Date.now() > Number(value.exp)) return null;
    return value as T;
  } catch {
    return null;
  }
}

export function createVerifyState(guildId: string): string {
  const value: VerifyState = {
    guildId,
    nonce: randomBytes(18).toString("base64url"),
    exp: Date.now() + 10 * 60 * 1000,
  };
  const body = encode(value);
  return `${body}.${signature(body)}`;
}

export function readVerifyState(token: string): VerifyState | null {
  return readSigned<VerifyState>(token);
}

export function createVerifyResult(value: Omit<VerifyResult, "exp">): string {
  const body = encode({ ...value, exp: Date.now() + 10 * 60 * 1000 });
  return `${body}.${signature(body)}`;
}

export function readVerifyResult(token: string): VerifyResult | null {
  return readSigned<VerifyResult>(token);
}

export function websiteOrigin(): string {
  return (
    process.env.NEXTAUTH_URL ||
    process.env.WEBSITE_URL ||
    "http://localhost:3000"
  ).replace(/\/$/, "");
}
