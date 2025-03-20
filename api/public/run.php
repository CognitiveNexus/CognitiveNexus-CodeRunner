<?php

require '../vendor/autoload.php';
use Docker\Docker;
use Docker\API\Model\ContainersCreatePostBody;
use Docker\API\Model\HostConfig;

header('Content-Type: application/json');
$uuid = uuid_create();
$projRoot = realpath(__DIR__ . '/../../');
$tmpDir = "{$projRoot}/tmp/coderun-{$uuid}";
mkdir($tmpDir, 0700);

try {
    $post = json_decode(file_get_contents('php://input'), true);
    if($post['usst'] != '1906') throw new Exception('unauthorized');
    $code = $post['code'] ?? '';
    $stdin = $post['stdin'] ?? '';
    file_put_contents("{$tmpDir}/code.c", $code);
    file_put_contents("{$tmpDir}/stdin", $stdin);

    $dockerLog = '';
    $docker = Docker::create();
    $containerConfig = new ContainersCreatePostBody();
    $containerConfig->setImage('code-runner');
    $containerConfig->setCmd(['/scripts/start.sh']);
    $containerConfig->setUser(posix_getuid().':'.posix_getgid());
    $containerConfig->setAttachStdout(true);
    $containerConfig->setAttachStderr(true);
    $hostConfig = new HostConfig();
    $hostConfig->setCapDrop(['ALL']);
    $hostConfig->setSecurityOpt(['no-new-privileges']);
    $hostConfig->setNetworkMode('none');
    $hostConfig->setMemory(256 * 1024 * 1024);
    $hostConfig->setNanoCpus(200000000);
    $hostConfig->setBinds(["{$tmpDir}:/sandbox"]);
    $hostConfig->setAutoRemove(true);
    $containerConfig->setHostConfig($hostConfig);
    $container = $docker->containerCreate($containerConfig);
    $docker->containerStart($container->getId());
    $docker->containerWait($container->getId());
    $data = file_get_contents("{$tmpDir}/dump.json");
    if($data === false) {
        throw new Exception('empty result');
    }

    $result = [
        'status' => 'success',
        'data' => json_decode($data, true),
    ];
} catch (Exception $e) {
    $result = [
        'status' => 'error',
        'message' => $e->getMessage(),
    ];
} finally {
    $result['logs'] = [
        'compile' => file_get_contents("{$tmpDir}/compile.log"),
        'run' => file_get_contents("{$tmpDir}/run.log"),
    ];
    echo json_encode($result);
    array_map('unlink', glob("{$tmpDir}/*"));
    rmdir($tmpDir);
}
