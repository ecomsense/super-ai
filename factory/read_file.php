<?php
# add basedir in ispconfig panel and then add the full path here
$filepath = '/opt/shared/files/data.txt';

if (file_exists($filepath)) {
    $lines = file($filepath, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    $last_lines = array_slice($lines, -20);
    $reversed_lines = array_reverse($last_lines);

    foreach ($reversed_lines as $line) {
        echo nl2br(htmlspecialchars($line)) . "\n";
    }
} else {
    echo "File not found.";
}
?>

