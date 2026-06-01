<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

<template>
  <div class="max-w-4xl mx-auto px-6 py-6 space-y-6">
    <RouterLink to="/review/" class="text-sm text-blue-600 hover:underline"
      >← Back to project overview</RouterLink
    >
    <p class="mt-2 text-gray-600 py-6">
      A web interface for reviewing the results of a license scan performed by the
      <a
        href="https://github.com/oss-review-toolkit/ort"
        target="_blank"
        rel="noopener"
        class="text-blue-600 hover:underline"
        >OSS Review Toolkit (ORT)</a
      >.
    </p>

    <div class="border-t py-6 space-y-3">
      <h2 class="text-lg font-semibold text-gray-800">What you can do</h2>
      <ul class="list-disc list-inside text-gray-600 space-y-1">
        <li>Browse packages and their license scan findings</li>
        <li>Add path excludes to ignore irrelevant files</li>
        <li>Create license finding curations for each scan result</li>
        <li>
          <!---->Conclude package licenses when you trust the declared licenses or reviewed all
          findings and sub-packages
        </li>
      </ul>
    </div>

    <div class="border-t py-6 space-y-3">
      <h2 class="text-lg font-semibold text-gray-800">How it works</h2>
      <p class="text-gray-600">
        The tool reads an ORT <code class="bg-gray-100 px-1 rounded">scan-result.yml</code> file and
        writes review decisions back to ORT configuration files (<code
          class="bg-gray-100 px-1 rounded"
          >package-configurations.yml</code
        >
        and <code class="bg-gray-100 px-1 rounded">curations.yml</code>).
      </p>
    </div>
  </div>
</template>
