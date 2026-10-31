import type { CodelandCityModel } from "./city-model";

export const SUPPORTED_SCHEMA_VERSION: CodelandCityModel["schemaVersion"] = "0.4.0";

/** Loads ?model=<url>, or public/city.json by default. */
export async function loadDefaultModel(): Promise<CodelandCityModel> {
  const url =
    new URLSearchParams(window.location.search).get("model") ??
    `${import.meta.env.BASE_URL}city.json`;
  const response = await fetch(url);
  // The dev server answers unknown paths with index.html, so check the content type too.
  if (!response.ok || !response.headers.get("content-type")?.includes("json")) {
    throw new Error(
      `Não encontrei ${url}. Gere um com: uv run codeland-analyze <repo> -o ../renderer/public/city.json`,
    );
  }
  return parseModel(await response.json());
}

export function parseModel(data: unknown): CodelandCityModel {
  const version = (data as { schemaVersion?: unknown } | null)?.schemaVersion;
  if (version !== SUPPORTED_SCHEMA_VERSION) {
    throw new Error(
      `Modelo com schemaVersion ${String(version)}; este renderizador lê ${SUPPORTED_SCHEMA_VERSION}.`,
    );
  }
  return data as CodelandCityModel;
}
