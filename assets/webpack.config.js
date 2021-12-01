const path = require("path");
const webpack = require("webpack");
const BundleTracker = require("webpack-bundle-tracker");

const resolve = path.resolve.bind(path, __dirname);

module.exports = (env, argv) => {
  let output, outputPath, publicPath;

  switch (env.env) {
    case "prod":
      publicPath = "https://example.com/static/bundles/prod/";
      outputPath = resolve("bundles/prod");
      break;
    case "dev":
      publicPath = "http://127.0.0.1:8000/static/bundles/dev/";
      outputPath = resolve("bundles/dev");
      break;
  }

  switch (argv.mode) {
    case "production":
      output = {
        path: outputPath,
        filename: "[chunkhash]/[name].js",
        chunkFilename: "[chunkhash]/[name].[id].js",
        publicPath: publicPath
      };
      break;

    case "development":
      output = {
        path: outputPath,
        filename: "[name].js",
        chunkFilename: "[name].js",
        publicPath: publicPath
      };
      break;

    default:
      break;
  }

  return {
    mode: argv.mode,
    entry: "./index.js",
    output,
    module: {
      rules: [
        // Scripts
        {
          test: /\.js$/,
          exclude: /node_modules/,
          loader: "babel-loader"
        },
        // Styles
        {
          test: /\.(sa|sc|c)ss$/,
          use: [
            {
              loader: "style-loader"
            },
            {
              loader: "css-loader",
              options: {
                sourceMap: true
              }
            },
            {
              loader: "sass-loader",
              options: {
                sourceMap: true
              }
            }
          ]
        }
      ]
    },
    plugins: [
      new BundleTracker({
        filename: `bundles/webpack-bundle.${env.env}.json`
      }),
    ],
    devtool: "source-map"
  };
};
