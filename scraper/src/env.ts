import { config } from 'dotenv';
import { existsSync } from 'node:fs';
import { resolve, isAbsolute, dirname } from 'node:path';

(function loadEnv() {
  // Load local .env first (lower precedence)
  const localEnvPath = resolve(process.cwd(), '.env');
  if (existsSync(localEnvPath)) {
    config({ path: localEnvPath, override: false });
  }

  // Load parent repo root .env (higher precedence)
  const parentEnvPath = resolve(process.cwd(), '..', '.env');
  let parentLoaded = false;
  if (existsSync(parentEnvPath)) {
    config({ path: parentEnvPath, override: true });
    parentLoaded = true;
  }

  // Normalize DB_PATH to absolute if it came from parent and is relative
  const dbPath = process.env.DB_PATH;
  if (parentLoaded && dbPath && !isAbsolute(dbPath)) {
    process.env.DB_PATH = resolve(dirname(parentEnvPath), dbPath);
  }
})();