// craco.config.js
const path = require("path");
require("dotenv").config();

const enableHealthCheck = process.env.ENABLE_HEALTH_CHECK === "true";

function makeDevServerV5Compatible(devServerConfig) {
  const { https, onAfterSetupMiddleware, onBeforeSetupMiddleware, onListening, setupMiddlewares, ...compatibleConfig } = devServerConfig;
  compatibleConfig.server = typeof https === "object" ? { type: "https", options: https } : https ? "https" : "http";
  compatibleConfig.headers = { ...compatibleConfig.headers, "Cross-Origin-Resource-Policy": "same-origin" };
  if (onBeforeSetupMiddleware || setupMiddlewares) {
    compatibleConfig.setupMiddlewares = (middlewares, devServer) => {
      if (onBeforeSetupMiddleware) onBeforeSetupMiddleware(devServer);
      return setupMiddlewares ? setupMiddlewares(middlewares, devServer) : middlewares;
    };
  }
  compatibleConfig.onListening = (devServer) => {
    devServer.close ??= (callback) => devServer.stopCallback(callback);
    if (onListening) onListening(devServer);
    if (onAfterSetupMiddleware) onAfterSetupMiddleware(devServer);
  };
  return compatibleConfig;
}

let healthPlugin;
let setupHealthEndpoints;
if (enableHealthCheck) {
  const WebpackHealthPlugin = require("./plugins/health-check/webpack-health-plugin");
  setupHealthEndpoints = require("./plugins/health-check/health-endpoints");
  healthPlugin = new WebpackHealthPlugin();
}

module.exports = {
  eslint: {
    configure: {
      extends: ["plugin:react-hooks/recommended"],
      rules: { "react-hooks/rules-of-hooks": "error", "react-hooks/exhaustive-deps": "warn" },
    },
  },
  webpack: {
    alias: { "@": path.resolve(__dirname, "src") },
    configure: (webpackConfig) => {
      webpackConfig.watchOptions = {
        ...webpackConfig.watchOptions,
        ignored: ["**/node_modules/**", "**/.git/**", "**/build/**", "**/dist/**", "**/coverage/**", "**/public/**"],
      };
      if (healthPlugin) webpackConfig.plugins.push(healthPlugin);
      return webpackConfig;
    },
  },
  devServer: (devServerConfig) => {
    if (healthPlugin) {
      const original = devServerConfig.setupMiddlewares;
      devServerConfig.setupMiddlewares = (middlewares, devServer) => {
        if (original) middlewares = original(middlewares, devServer);
        setupHealthEndpoints(devServer, healthPlugin);
        return middlewares;
      };
    }
    return makeDevServerV5Compatible(devServerConfig);
  },
};
