/**
 * 检查 npm registry 上是否有比当前版本更新的版本，若有则在终端打印升级提示。
 *
 * 使用 `update-notifier`（纯 ESM 包）实现，由于本项目编译产物是 CommonJS，
 * 这里用动态 `import()` 加载它。update-notifier 内部已处理：
 * - 缓存（默认 1 天查一次，结果写入用户配置目录）
 * - CI / 非 TTY 环境静默
 * - `NO_UPDATE_NOTIFIER` 环境变量开关
 *
 * 任何异常都被静默吞掉，升级提示绝不会影响 CLI 主流程。
 */
export declare function notifyUpdate(pkg: {
    name: string;
    version: string;
}): Promise<void>;
