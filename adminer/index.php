<?php
namespace docker {
	function adminer_object() {
		/**
		 * Prefills the “Server” field with the ADMINER_DEFAULT_SERVER environment variable.
		 */
		final class DefaultServerPlugin extends \Adminer\Plugin {
			public function __construct(
				private \Adminer\Adminer $adminer
			) { }

			public function loginFormField(...$args): string {
				return (function (...$args): string {
					$field = $this->loginFormField(...$args);

					return \preg_replace_callback(
						"/name='auth\[server\]' value='' title='(?:[^']+)'/",
						static function (array $matches): string {
							return \str_replace(
								"value=''",
								\sprintf("value='%s'", ($_ENV['ADMINER_DEFAULT_SERVER'] ?: 'db')),
								$matches[0],
							);
						},
						$field,
					);
				})->call($this->adminer, ...$args);
			}
		}

		$plugins = [];
		foreach (glob('plugins-enabled/*.php') as $plugin) {
			$plugins[] = require($plugin);
		}

		$adminer = new \Adminer\Plugins($plugins);

		(function () {
			$last = &$this->hooks['loginFormField'][\array_key_last($this->hooks['loginFormField'])];
			if ($last instanceof \Adminer\Adminer) {
				$defaultServerPlugin = new DefaultServerPlugin($last);
				$this->plugins[] = $defaultServerPlugin;
				$last = $defaultServerPlugin;
			}
		})->call($adminer);

		return $adminer;
	}
}

namespace {
	if (basename($_SERVER['DOCUMENT_URI'] ?? $_SERVER['REQUEST_URI']) === 'adminer.css' && is_readable('adminer.css')) {
		header('Content-Type: text/css');
		readfile('adminer.css');
		exit;
	}

	function adminer_object() {
		return \docker\adminer_object();
	}

	// ── Dev-stack autologin ────────────────────────────────────────────────
	// Seeds the login POST from the environment so a developer never types
	// credentials. Adminer only consults a plugin's credentials() hook once a
	// password is already in the session, which is circular for a first visit —
	// so the login has to be seeded as a POST. An explicit ?username= in the URL
	// is left alone, so a deliberate login still wins.
	//
	// This replaces the stock index.php. It keeps the original
	// adminer_object() declaration verbatim: defining that function in a
	// separate file as well is a fatal "Cannot redeclare function" error.
	if (!$_GET && !$_POST) {
		$_POST['auth'] = [
			'driver' => $_ENV['ADMINER_DEFAULT_DRIVER'] ?: 'pgsql',
			'server' => $_ENV['ADMINER_DEFAULT_SERVER'] ?: 'db',
			'username' => $_ENV['ADMINER_DEFAULT_USERNAME'] ?: 'bootcamp',
			'password' => $_ENV['ADMINER_DEFAULT_PASSWORD'] ?: 'bootcamp',
			'db' => $_ENV['ADMINER_DEFAULT_DB'] ?: 'bootcamp_connect',
		];
	}

	require('adminer.php');
}