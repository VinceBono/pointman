# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vince Bono
#
# A small window for the integration test: a text box, a password box, a button and a status label.
Add-Type -AssemblyName System.Windows.Forms

$form = New-Object System.Windows.Forms.Form
$form.Text = "Pointman Test Target"
$form.Width = 360
$form.Height = 220

$name = New-Object System.Windows.Forms.TextBox
$name.AccessibleName = "Name"
$name.SetBounds(20, 20, 300, 24)

$secret = New-Object System.Windows.Forms.TextBox
$secret.AccessibleName = "Secret"
$secret.UseSystemPasswordChar = $true
$secret.Text = "hunter2"
$secret.SetBounds(20, 55, 300, 24)

$status = New-Object System.Windows.Forms.Label
$status.Text = "waiting"
$status.SetBounds(20, 130, 300, 24)

$button = New-Object System.Windows.Forms.Button
$button.Text = "Greet"
$button.SetBounds(20, 90, 100, 28)
$button.Add_Click({ $status.Text = "hello " + $name.Text })

$form.Controls.AddRange(@($name, $secret, $button, $status))
[System.Windows.Forms.Application]::Run($form)
