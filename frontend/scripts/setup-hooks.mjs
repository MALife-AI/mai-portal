#!/usr/bin/env node
/**
 * npm install 시 자동으로 실행되는 Husky 설정 스크립트.
 * - frontend/는 모노레포가 아닌 서브디렉터리이므로 git 훅을 repo root의
 *   .husky/로 가리키도록 core.hooksPath 를 로컬 설정에 기록한다.
 * - CI(CI=true)나 git 외 환경에선 조용히 스킵.
 */
import { execSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { join, resolve } from 'node:path'

if (process.env.CI) {
  process.exit(0)
}

try {
  const repoRoot = execSync('git rev-parse --show-toplevel', {
    stdio: ['ignore', 'pipe', 'ignore'],
  }).toString().trim()

  const huskyDir = join(repoRoot, '.husky')
  if (!existsSync(huskyDir)) {
    // .husky 디렉터리가 없으면 훅을 활성화할 대상이 없으므로 스킵
    process.exit(0)
  }

  // git 하위에서만 실행 (submodule 등 고려)
  const inWorkTree = execSync('git rev-parse --is-inside-work-tree', {
    cwd: repoRoot,
    stdio: ['ignore', 'pipe', 'ignore'],
  }).toString().trim()
  if (inWorkTree !== 'true') process.exit(0)

  execSync('git config core.hooksPath .husky', { cwd: repoRoot, stdio: 'ignore' })
  // 상대 경로로 보기 좋게 출력
  const rel = resolve(huskyDir)
  console.log(`husky: ${rel} 로 core.hooksPath 설정됨`)
} catch {
  // git 없는 환경 (tarball install 등) — 무시
}
