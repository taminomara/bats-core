load helper

@test "helper" {
  run say_hi
  [ "$status" -eq 0 ]
  [ "$output" = "hi" ]
}
