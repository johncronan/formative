const path = require("path");
const webpack = require("webpack");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");
const CssMinimizerPlugin = require("css-minimizer-webpack-plugin");
const autoprefixer = require("autoprefixer");
const TerserPlugin = require('terser-webpack-plugin');

const resolve = path.resolve.bind(path, __dirname);

module.exports = (env, argv) => {
  let ret, output, outputPath, publicPath, cssFilename;

  switch (env.env) {
    case "prod":
      publicPath = "/static/bundles/prod/";
      outputPath = resolve("bundles/prod");
      cssFilename = "[name].css";
      break;
    case "dev":
      publicPath = "/static/bundles/dev/";
      outputPath = resolve("bundles/dev");
      cssFilename = "[name].css";
      break;
  }

  output = {
    path: outputPath,
    filename: "[name].js",
    chunkFilename: "[name]-[id].[contenthash].js",
    publicPath: publicPath
  };

  ret = {
    mode: argv.mode,
    entry: {
      'es6-promise': './js/es6-promise.js',
      'formative': './formative.js'
    },
    target: ['web', 'es5'],
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
                sourceMap: false //argv.mode != 'production',
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
                sourceMap: argv.mode != 'production',
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
      new MiniCssExtractPlugin({
        filename: cssFilename
      })
    ],
    optimization: {
      minimizer: [
        new TerserPlugin(),
        new CssMinimizerPlugin()
      ]
    }
  };
  if (argv.mode != 'production') {
    ret.plugins.push(new webpack.SourceMapDevToolPlugin({
      filename: '[name].map'
    }));
  }
  return ret;
};
