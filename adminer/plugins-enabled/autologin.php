<?php
/**
 * Adminer autologin plugin for the dev stack.
 *
 * Supplying server/username/password from the environment means a developer
 * never types credentials — which is also how the hyphenated
 * "bootcamp-connect" typo got in: a hand-typed database name is exactly the
 * thing this plugin exists to remove.
 *
 * Note the password comes from the environment, NOT from get_password().
 * The version of this plugin published in docker-adminer#13 returns
 * get_password(), which is null before a session exists, so the first
 * connection attempt fails with a bare 403 and the login form reappears.
 */

return new class extends \Adminer\Plugin {
    public function credentials(): array
    {
        return [
            $_ENV['ADMINER_DEFAULT_SERVER'] ?: 'db',
            $_ENV['ADMINER_DEFAULT_USERNAME'] ?: 'bootcamp',
            $_ENV['ADMINER_DEFAULT_PASSWORD'] ?: 'bootcamp',
        ];
    }
};