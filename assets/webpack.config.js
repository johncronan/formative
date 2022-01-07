const path = require("path");
const webpack = require("webpack");
const BundleTracker = require("webpack-bundle-tracker");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");
const autoprefixer = require("autoprefixer");

const resolve = path.resolve.bind(path, __dirname);

module.exports = (env, argv) => {
  let output, outputPath, publicPath;

  switch (env.env) {
    case "prod":
      publicPath = "https://example.com/static/bundles/prod/";
      outputPath = resolve("bundles/prod");
      break;
    case "dev":
      publicPath = "/static/bundles/dev/";
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
    entry: {
      'es6-promise': './js/es6-promise.js',
      'apply': './apply.js',
      'review': './review.js',
    },
    output,
    module: {
      rules: [
        // Styles
        {
          test: /\.(sa|sc|c)ss$/,
          use: [
            {
              loader: MiniCssExtractPlugin.loader
            },
            {
              loader: "css-loader",
              options: {
                sourceMap: true,
              }
            },
            {
              loader: "postcss-loader",
              options: {
                postcssOptions: {
                  plugins: [autoprefixer()]
                }
              }
            },
            {
              loader: "sass-loader",
              options: {
                sourceMap: true,
                sassOptions: {
                  includePaths: ['./node_modules']
                }
              }
            }
          ]
        },
        // Scripts
        {
          test: /\.js$/,
          exclude: /node_modules/,
          loader: "babel-loader",
          options: {
            presets: ['@babel/preset-env']
          }
        }
      ]
    },
    plugins: [
      new BundleTracker({
        filename: `bundles/webpack-bundle.${env.env}.json`
      }),
      new MiniCssExtractPlugin()
    ],
    devtool: "source-map"
  };
};
