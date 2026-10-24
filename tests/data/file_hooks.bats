setup_file() {
  echo "setup_file ran" >&3
}

teardown_file() {
  echo "teardown_file ran" >&3
}

@test "hooked" {
  true
}
